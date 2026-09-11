"""One native CLI session in the owned gateway worker, never a nested tool loop."""
import time
from .cross_harness_process import start_owned_process
from .gateway_cli_events import NativeEvents
from .gateway_cli_profiles import session_argv
from .gateway_cli_runtime import (verify_runtime, pin_runtime, session_env,
                                  check_configuration_boundary)
from .gateway_operation import GatewayOperationError
from .gateway_cli_profile_home import owned_profile_home


def run_cli_session(goal, binding, root, deadline, emit, *, launcher=None,
                    state_root=None, state_identity=None):
    runtime, profile = binding['cli_runtime'], binding['cli_session']
    check_configuration_boundary(profile['provider'], root)
    verify_runtime(runtime)
    argv = session_argv(runtime['executable'], profile, binding['model']['model_id'],
                        root, binding['budget']['max_steps'])
    if type(goal) is not str or len(goal.encode('utf-8')) > 1024 * 1024:
        raise GatewayOperationError('AGENT_CLI_PROTOCOL_ERROR')
    parser = NativeEvents(profile['provider'], profile['tools'], emit,
                           max_steps=binding['budget']['max_steps'])
    process, consumed = None, 0
    def read_events(raw, *, final=False):
        nonlocal consumed
        end = len(raw) if final else raw.rfind(b'\n') + 1
        if end < consumed: raise GatewayOperationError('AGENT_CLI_PROTOCOL_ERROR')
        try: text = raw[consumed:end].decode('utf-8', 'strict')
        except UnicodeError: raise GatewayOperationError('AGENT_CLI_PROTOCOL_ERROR') from None
        for line in text.splitlines(): parser.feed(line)
        consumed = end
    with pin_runtime(runtime), owned_profile_home(
            state_root=state_root, state_identity=state_identity) as profile_home:
        env = session_env(profile['provider'], runtime['auth_directory'], profile_home)
        try:
            if time.monotonic() >= deadline:
                raise GatewayOperationError('OPERATION_DEADLINE_EXCEEDED')
            process = (launcher or start_owned_process)(argv, cwd=root,
                stdin_bytes=goal.encode('utf-8'), env=env, hide_window=True)
            if not process.resume(): raise GatewayOperationError('AGENT_CLI_PROCESS_FAILED')
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise GatewayOperationError('OPERATION_DEADLINE_EXCEEDED')
                outcome = process.wait(min(.05, remaining))
                raw, overflow = process.stdout_snapshot()
                if overflow or process.capture_overflow():
                    raise GatewayOperationError('AGENT_CLI_PROTOCOL_ERROR')
                read_events(raw)
                if outcome is not None:
                    if outcome.returncode or outcome.timed_out:
                        raise GatewayOperationError('AGENT_CLI_PROCESS_FAILED')
                    if outcome.malformed_output: raise GatewayOperationError('AGENT_CLI_PROTOCOL_ERROR')
                    read_events(outcome.stdout.encode('utf-8'), final=True)
                    return parser.finish()
        finally:
            if process is not None: process.close()
