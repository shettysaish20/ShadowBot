
## Pending Tasks

### 1. Answer Alignment
- Add server shutdown button on the app; Add continue previous session button as well
- Show query asked to the user (if from text)
- Refine the FormatterAgent to answer in first person so that the user can repeat exact same thing

### 2. Historic Session re-hydration
- Render the historic session and continue conversation from where it was left off
- Show the original query on the listing section of session ID

### 3. Image Refinement
- The screenshot is taken when the SS button is clicked on the app (button should then turn green), that image is stored in memory
- Memory should be released after the query is sent to backend, and another screenshot should not be taken until the SS button is clicked again
- If no screenshot is taken, then if the user sends a query then it should go to backend without any image input

### 4. Audio integration with BE:
- Send audio transcription to the backend along with screenshot
- Limit the frequency to trigger the call to Backend for Audio transcription (probably do it using a keyboard shortcut instead of gap)

