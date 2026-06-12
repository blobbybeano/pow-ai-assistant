import 'package:flutter/foundation.dart';

import '../models/integration_settings.dart';
import '../services/chat_api_client.dart';

class IntegrationSettingsController extends ChangeNotifier {
  IntegrationSettingsController({required ChatApiClient apiClient})
      : _apiClient = apiClient;

  final ChatApiClient _apiClient;

  IntegrationSettings? _settings;
  bool _isLoading = false;
  bool _isSaving = false;
  Object? _error;

  IntegrationSettings? get settings => _settings;
  bool get isLoading => _isLoading;
  bool get isSaving => _isSaving;
  Object? get error => _error;

  Future<IntegrationSettings?> load() async {
    _isLoading = true;
    _error = null;
    notifyListeners();
    try {
      _settings = await _apiClient.fetchIntegrationSettings();
      return _settings;
    } catch (err) {
      _error = err;
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<IntegrationSettings?> save(IntegrationSettingsUpdate update) async {
    _isSaving = true;
    _error = null;
    notifyListeners();
    try {
      _settings = await _apiClient.updateIntegrationSettings(update);
      return _settings;
    } catch (err) {
      _error = err;
      rethrow;
    } finally {
      _isSaving = false;
      notifyListeners();
    }
  }

  Future<ConnectionTestResult> testTwilioConnection() {
    return _apiClient.testTwilioConnection();
  }

  Future<ConnectionTestResult> testOpenAiConnection() {
    return _apiClient.testOpenAiConnection();
  }

  void reset() {
    _settings = null;
    _error = null;
    _isLoading = false;
    _isSaving = false;
    notifyListeners();
  }
}
