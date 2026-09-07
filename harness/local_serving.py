"""Explicit local serving settings; omitted settings remain server-controlled."""
import re


def validate_num_ctx(value):
    if value is not None and (type(value) is not int or not 1 <= value <= 1048576):
        raise ValueError('num_ctx must be an integer from 1 to 1048576, or omitted')
    return value


def context_argument(value):
    return validate_num_ctx(int(value))


def profile_num_ctx(profile):
    config = profile.get('generation_config', {})
    if not isinstance(config, dict) or set(config) - {'num_ctx'}:
        raise ValueError('unsupported local generation_config')
    return validate_num_ctx(config.get('num_ctx'))


def profile_config_error(profile):
    if profile.get('backend') not in {'serve', 'ollama'}:
        return 'unsupported_local_backend'
    if profile.get('backend') == 'ollama':
        try:
            profile_num_ctx(profile)
        except ValueError:
            return 'invalid_generation_config'
    return ''


def generation_config(backend, max_tokens, temperature, seed):
    result = {'temperature': temperature, 'seed': seed, 'num_predict': max_tokens}
    context = validate_num_ctx(backend.num_ctx)
    if context is not None:
        result['num_ctx'] = context
    return result


def configure_profiles(profiles, context, models):
    context = validate_num_ctx(context)
    for key, name in (models or {}).items():
        if key not in {'14b', '32b'} or not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}', name):
            raise ValueError('invalid Ollama model selector')
    for row in profiles:
        if row['backend'] != 'ollama':
            continue
        row['generation_config'] = {} if context is None else {'num_ctx': context}
        selected = (models or {}).get(row['model_key'])
        if selected and row['profile_id'] == f"ollama-{row['model_key']}":
            row.update(selectors=[selected], model_ref=f'ollama:{selected}',
                       launch_command_template=f'ollama run {selected}')
