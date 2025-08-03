import re
import os
from urllib.parse import urlparse
import requests
from typing import List, Tuple, Callable

class QueryHeuristics:
    def __init__(self):
        # Blacklisted words - can be expanded
        self.blacklist = {
            'spam', 'hack', 'crack', 'illegal', 'exploit',
            'password', 'credit card', 'ssn', 'private'
        }
        
        # Register heuristic rules - easy to add more
        self.rules: List[Tuple[str, Callable[[str], Tuple[bool, str]]]] = [
            ("URL Validation", self._check_url),
            ("File Path Validation", self._check_file_path),
            ("Sentence Length", self._check_sentence_length),
            ("Blacklist Check", self._check_blacklist),
            ("URL Protocol Check", self._check_url_protocol)
        ]

    def _extract_urls_from_text(self, text: str) -> List[Tuple[str, str]]:
        """
        Extract URLs from natural language text
        Returns list of (original_url, processed_url) tuples
        """
        # Match both full URLs and domain-like patterns
        url_patterns = [
            # Full URLs with protocol
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            # Domain-like patterns (e.g., www.example.com or example.com)
            r'(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+(?:/[^\s]*)?'
        ]
        
        found_urls = []
        for pattern in url_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                url = match.group()
                # Skip if already has protocol
                if url.startswith(('http://', 'https://')):
                    found_urls.append((url, url))
                else:
                    # Add https:// for security
                    processed_url = f'https://{url}' if not url.startswith('www.') else f'https://{url[4:]}'
                    found_urls.append((url, processed_url))
        
        return found_urls

    def _check_url(self, query: str) -> Tuple[bool, str]:
        """Enhanced URL validation for natural language queries"""
        urls = self._extract_urls_from_text(query)
        
        if not urls:
            return True, "No URLs found in query"
            
        for _, processed_url in urls:
            try:
                response = requests.head(processed_url, timeout=5)
                if response.status_code >= 400:
                    return False, f"URL {processed_url} is not accessible"
            except requests.RequestException:
                return False, f"Failed to connect to {processed_url}"
        
        return True, "All URLs in query are valid and accessible"

    def _check_file_path(self, query: str) -> Tuple[bool, str]:
        """Check if file paths in the query are valid"""
        # Match common file path patterns
        path_pattern = r'(?:\/[\w.-]+)+|(?:[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*)'
        paths = re.findall(path_pattern, query)
        
        if not paths:
            return True, "No file paths found"
            
        for path in paths:
            if not os.path.exists(path):
                return False, f"File path does not exist: {path}"
        
        return True, "All file paths are valid"

    def _check_sentence_length(self, query: str) -> Tuple[bool, str]:
        """Check if sentences are within length limit"""
        # Split by common sentence terminators and remove empty strings
        sentences = [s.strip() for s in re.split(r'[.!?]+', query) if s.strip()]
        max_length = 100
        
        for sentence in sentences:
            if len(sentence) > max_length:
                return False, f"Sentence exceeds {max_length} characters:\n'{sentence[:50]}...' ({len(sentence)} characters)"
            
            # Check for repetitive patterns that might indicate concatenation
            words = sentence.split()
            if len(words) >= 4:  # Check patterns of 4 or more words
                word_pattern = ' '.join(words[:4])  # Take first 4 words
                if sentence.count(word_pattern) > 1:
                    return False, f"Detected repetitive pattern: '{word_pattern}...'"
        
        return True, f"All sentences are within {max_length} character limit"

    def _check_blacklist(self, query: str) -> Tuple[bool, str]:
        """Check for blacklisted words"""
        query_lower = query.lower()
        found_words = [word for word in self.blacklist if word in query_lower]
        
        if found_words:
            return False, f"Found blacklisted words: {', '.join(found_words)}"
        
        return True, "No blacklisted words found"

    def _check_url_protocol(self, query: str) -> Tuple[bool, str]:
        """Enhanced URL protocol check for natural language queries"""
        urls = self._extract_urls_from_text(query)
        modified_query = query
        
        if not urls:
            return True, "No URLs found in query"
            
        changes_made = False
        for original, processed in urls:
            if original != processed:
                modified_query = modified_query.replace(original, processed)
                changes_made = True
        
        if changes_made:
            return False, f"Modified query with proper URL protocols: {modified_query}"
        
        return True, "All URLs have proper protocols"

    def _sanitize_blacklisted_words(self, text: str) -> str:
        """Replace blacklisted words with XXXX"""
        sanitized = text.lower()
        for word in self.blacklist:
            if word in sanitized:
                # Replace with XXXX of same length as the word
                text = text.replace(word, 'X' * len(word))
                text = text.replace(word.upper(), 'X' * len(word))
        return text

    def process(self, query: str) -> Tuple[bool, str, str]:
        """
        Process query through sanitization
        Returns: (passed_all, message, sanitized_query)
        """
        sanitized_query = self._sanitize_blacklisted_words(query)
        
        # Return message only if changes were made
        if sanitized_query != query:
            return False, f"Sanitized blacklisted words", sanitized_query
        
        return True, "", query

    def add_rule(self, name: str, rule_func: Callable[[str], Tuple[bool, str]]):
        """Add a new heuristic rule"""
        self.rules.append((name, rule_func))

    def add_blacklist_words(self, words: List[str]):
        """Add new words to blacklist"""
        self.blacklist.update(words)
