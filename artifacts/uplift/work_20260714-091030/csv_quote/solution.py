def csv_quote(field):
    if not isinstance(field, str):
        raise ValueError('bad field')
    needs = any(c in field for c in ',\r\n"')
    if not needs:
        return field
    return '"' + field.replace('"', '""') + '"'
