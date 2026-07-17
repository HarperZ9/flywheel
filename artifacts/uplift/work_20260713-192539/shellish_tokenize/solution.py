def tokenize_quoted(s: str) -> list[str]:
    def process_segment(start):
        tokens = []
        while start < len(s):
            if s[start] == '"':
                quote_handler(tokens, start)
            elif s[start] == "'":
                single_quote_handler(tokens, start)
            else:
                word = find_next_word(start)
                if word:
                    tokens.append(word)
                    start += len(word)
        return tokens

    def find_next_word(start):
        end = start
        while end < len(s) and not (s[end] in '"\' ' + '\t'):
            end += 1
        return s[start:end]

    def quote_handler(tokens, start):
        state = "start"
        text = ""
        escape_count = 0
        bracket_level = 0

        for i in range(start + 1, len(s)):
            if s[i] == '"':
                if escape_count % 2 == 0 and not bracket_level:
                    tokens.append(text)
                    text = ""
                    escape_count = 0
                else:
                    if (s[i] == '\\' and escape_count % 2 == 1) or (i < len(s) - 1 and s[i+1] != '"'):
                        text += s[i]
                        escape_count += 1
                    elif i == len(s) - 1:
                        raise ValueError("Unterminated quoted segment")
                    else:
                        bracket_level = 0 if s[i + 1:i + 2] not in '()[]{}' else bracket_level + (1 if s[i + 1:i + 2] in '{[' else -1)
                        tokens.append(text) if text else None
                        return quote_handler(tokens, i + 2 if s[i + 1:i + 2] in '{}([' else i + 2)
                escape_count = 0
            elif s[i] == '\\':
                if not state or (state == 'start' and bracket_level):
                    tokens.append(text) if text else None
                    text += s[i]
                    escape_count = 1 if escape_count % 2 == 0 else 0
                else:
                    escape_count += 1
            elif escape_count % 2 == 0:
                state = "escape" if s[i] in '"\' ' + '\t' else "normal"
                text += s[i]
        if escape_count % 2 == 0 and not bracket_level:
            tokens.append(text)
        return quote_handler(tokens, start)

    def single_quote_handler(tokens, start):
        state = "start"
        text = ""
        for i in range(start + 1, len(s)):
            if s[i] == "'":
                tokens.append(text) if text else None
                break
            elif s[i] == '\\':
                if not state:
                    text += s[i]
                elif state == 'escape' and escape_count % 2 != 0 and i < len(s) - 1 and s[i + 1] in '"\' ' + '\t' and not bracket_level:
                    text += s[i:i+2]
                    escape_count = 1
            else:
                if state == "end" or (state == "start" and bracket_level):
                    tokens.append(text) if text else None
                    break
                state, text = ('normal', s[i]) if s[i] not in '"\' ' + '\t' else ('escape', s[i])
        return single_quote_handler(tokens, start)

    def check_for_missing_close(start, expected_type, is_double):
        if expected_type == "double":
            bracket_level = 0
            for i
