part of 'provider_session_surface.dart';

extension _ProviderSessionSurfaceBinding on _ProviderSessionSurfaceState {
  Future<void> _loadBinding() async {
    final generation = ++_bindingGeneration;
    final journey = _journeyBinding;
    final workspace = widget.workspaceRef;
    final permissionScope = _permissionScope;
    final key = _ProviderSessionBindingKey(
      client: widget.client,
      provider: widget.provider,
      journeyRef: journey?.journeyRef ?? '',
      expectedEventHead: journey?.eventHead ?? '',
      workspaceRef: workspace ?? '',
      model: _modelText,
      permissionScopeKey: permissionScope.toString(),
    );
    _update(() {
      _loadingBinding = true;
      _bindingError = null;
      _binding = null;
      _bindingKey = null;
    });
    if (journey == null) {
      _update(() {
        _bindingError = 'JOURNEY_REQUIRED';
        _loadingBinding = false;
      });
      return;
    }
    if (workspace == null || workspace.isEmpty) {
      _update(() {
        _bindingError = 'WORKSPACE_REQUIRED';
        _loadingBinding = false;
      });
      return;
    }
    try {
      final binding = await widget.client.providerSessionBinding(
        ProviderSessionBindingRequest(
          journeyRef: key.journeyRef,
          expectedEventHead: key.expectedEventHead,
          provider: key.provider,
          workspaceRef: key.workspaceRef,
          model: key.model,
          permissionScope: permissionScope,
        ),
      );
      if (!_isCurrentBindingRequest(generation, key) ||
          !_bindingMatchesRequest(key, binding)) {
        return;
      }
      _update(() {
        _binding = binding;
        _bindingKey = key;
        _bindingError = null;
      });
    } on Object catch (error) {
      if (!_isCurrentBindingRequest(generation, key)) return;
      _update(() {
        _bindingError = _bindingMessage(error);
      });
    } finally {
      if (mounted && _bindingGeneration == generation) {
        _update(() => _loadingBinding = false);
      }
    }
  }

  bool _isCurrentBindingRequest(
      int generation, _ProviderSessionBindingKey key) {
    final journey = _journeyBinding;
    return mounted &&
        _bindingGeneration == generation &&
        identical(widget.client, key.client) &&
        widget.provider == key.provider &&
        journey?.journeyRef == key.journeyRef &&
        journey?.eventHead == key.expectedEventHead &&
        (widget.workspaceRef ?? '') == key.workspaceRef &&
        _modelText == key.model &&
        _permissionScope.toString() == key.permissionScopeKey;
  }

  bool _bindingMatchesRequest(
          _ProviderSessionBindingKey key, ProviderSessionBinding binding) =>
      binding.provider == key.provider &&
      binding.journeyRef == key.journeyRef &&
      binding.workspaceRef == key.workspaceRef &&
      (binding.model.isEmpty ? null : binding.model) == key.model &&
      binding.observedAtEventHead == key.expectedEventHead;

  bool _bindingIsCurrent(ProviderSessionBinding binding) {
    final key = _bindingKey;
    return key != null &&
        identical(_binding, binding) &&
        _isCurrentBindingRequest(_bindingGeneration, key) &&
        _bindingMatchesRequest(key, binding);
  }

  GatewayJourneyBinding? get _journeyBinding {
    final element = context
        .getElementForInheritedWidgetOfExactType<GatewayOperationScope>();
    final scope = element?.widget as GatewayOperationScope?;
    return _bindingFromScope(scope);
  }

  GatewayJourneyBinding? get _journeyBindingDependency =>
      _bindingFromScope(GatewayOperationScope.maybeOf(context));

  GatewayJourneyBinding? _bindingFromScope(GatewayOperationScope? scope) {
    final projection = scope?.journey?.state.projection;
    if (projection == null || projection.invalidResponse) return null;
    return GatewayJourneyBinding(
      projection.journeyRef,
      projection.eventHeadSha256,
    );
  }

  Map<String, Object?> get _permissionScope => const {
        'mode': 'manual',
        'approval_policy': {
          'allow_tools': ['item/commandExecution/requestApproval'],
          'updated_input_keys': {
            'item/commandExecution/requestApproval': ['decision'],
          },
        },
      };
}

String _bindingMessage(Object error) {
  if (error is GatewayException && error.statusCode == 404) {
    return 'gateway binding read surface is missing';
  }
  if (error is GatewayException && error.errorCode != null) {
    return error.errorCode!;
  }
  return 'binding read failed';
}

final class _ProviderSessionBindingKey {
  final GatewayClient client;
  final String provider, journeyRef, expectedEventHead, workspaceRef;
  final String? model;
  final String permissionScopeKey;

  const _ProviderSessionBindingKey({
    required this.client,
    required this.provider,
    required this.journeyRef,
    required this.expectedEventHead,
    required this.workspaceRef,
    required this.model,
    required this.permissionScopeKey,
  });
}
