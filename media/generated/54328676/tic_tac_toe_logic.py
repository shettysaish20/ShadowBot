def create_board():
    return [[' ' for _ in range(3)] for _ in range(3)]


def check_win(board, player):
    # Check rows
    for row in board:
        if all(cell == player for cell in row):
            return True

    # Check columns
    for col in range(3):
        if all(board[row][col] == player for row in range(3)):
            return True

    # Check diagonals
    if all(board[i][i] == player for i in range(3)):
        return True
    if all(board[i][2 - i] == player for i in range(3)):
        return True

    return False


def check_draw(board):
    for row in board:
        if ' ' in row:
            return False
    return True


def make_move(board, row, col, player):
    if board[row][col] == ' ':
        board[row][col] = player
        return True
    else:
        return False

#UI_INTEGRATION_PLACEHOLDER#