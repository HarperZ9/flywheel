// Controller for the Codex account panel.

import 'package:flutter/foundation.dart';

import '../client/codex_account_client.dart';
import '../models/codex_account_models.dart';

final class CodexAccountController extends ChangeNotifier {
  final CodexAccountApi api;
  CodexAccountDoc? account;
  CodexLoginStart? login;
  CodexModelCatalog? catalog;
  CodexAccountPhase phase = CodexAccountPhase.unavailable;
  String message = 'Codex account state has not been read yet.';
  bool busy = false;
  bool _disposed = false;
  int _ticket = 0;

  CodexAccountController(this.api);

  Future<void> refresh() async {
    final ticket = _begin();
    try {
      final doc = await api.readAccount();
      if (!_active(ticket)) return;
      final nextCatalog = doc.phase == CodexAccountPhase.signedIn
          ? await api.readModelCatalog()
          : null;
      if (!_active(ticket)) return;
      account = doc;
      phase = doc.phase;
      message = doc.reason;
      catalog = nextCatalog;
      if (!_active(ticket)) return;
    } catch (e) {
      if (_active(ticket)) _fail('Codex account read failed: ${e.runtimeType}');
    } finally {
      _end(ticket);
    }
  }

  Future<void> startLogin(CodexLoginMode mode) async {
    final ticket = _begin();
    try {
      final started = await api.startLogin(mode);
      if (!_active(ticket)) return;
      if (started.loginId.isEmpty || started.launchUri == null) {
        _fail('Login start returned no accepted HTTPS OpenAI URL.');
        return;
      }
      login = started;
      phase = CodexAccountPhase.loginPending;
      message = 'Waiting for Codex account login result.';
    } catch (e) {
      if (_active(ticket)) {
        _fail('Codex login could not start: ${e.runtimeType}');
      }
    } finally {
      _end(ticket);
    }
  }

  Future<bool> refreshLoginResult() async {
    final current = login;
    if (current == null || current.loginId.isEmpty) return false;
    final ticket = _begin();
    var ready = false;
    try {
      final result = await api.loginResult(current.loginId);
      if (!_active(ticket)) return false;
      if (result.loginId.isNotEmpty && result.loginId != current.loginId) {
        _fail('Login result did not match the active login id.');
        return false;
      }
      if (result.pending) {
        phase = CodexAccountPhase.loginPending;
        message =
            result.reason.isEmpty ? 'Login is still pending.' : result.reason;
        return false;
      }
      if (result.cancelled) {
        login = null;
        phase = CodexAccountPhase.signedOut;
        message = 'Login cancelled.';
        return false;
      }
      if (!result.authenticated) {
        _fail(result.reason.isEmpty ? 'Codex login failed.' : result.reason);
        return false;
      }
      final doc = await api.readAccount();
      if (!_active(ticket)) return false;
      account = doc;
      if (!doc.chatGptSignedIn) {
        catalog = null;
        _fail('Account readback did not confirm ChatGPT sign-in.');
        return false;
      }
      final nextCatalog = await api.readModelCatalog();
      if (!_active(ticket)) return false;
      catalog = nextCatalog;
      login = null;
      phase = CodexAccountPhase.signedIn;
      message = doc.reason;
      ready = true;
    } catch (e) {
      if (_active(ticket)) _fail('Codex login result failed: ${e.runtimeType}');
    } finally {
      _end(ticket);
    }
    return ready;
  }

  Future<void> cancelLogin() async {
    final current = login;
    if (current == null || current.loginId.isEmpty) return;
    final ticket = _begin();
    try {
      await api.cancelLogin(current.loginId);
      if (!_active(ticket)) return;
      login = null;
      phase = CodexAccountPhase.signedOut;
      message = 'Login cancelled.';
    } catch (e) {
      if (_active(ticket)) _fail('Codex login cancel failed: ${e.runtimeType}');
    } finally {
      _end(ticket);
    }
  }

  Future<void> logout() async {
    final ticket = _begin();
    try {
      await api.logout();
      if (!_active(ticket)) return;
      login = null;
      catalog = null;
      phase = CodexAccountPhase.signedOut;
      message = 'Logout requested.';
    } catch (e) {
      if (_active(ticket)) _fail('Codex logout failed: ${e.runtimeType}');
    } finally {
      _end(ticket);
    }
  }

  int _begin() {
    busy = true;
    _ticket++;
    _emit();
    return _ticket;
  }

  bool _active(int ticket) => !_disposed && ticket == _ticket;

  void _end(int ticket) {
    if (!_active(ticket)) return;
    busy = false;
    _emit();
  }

  void _fail(String text) {
    phase = CodexAccountPhase.failed;
    message = text;
  }

  void _emit() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
