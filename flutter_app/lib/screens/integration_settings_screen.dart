import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/integration_settings_controller.dart';
import '../models/integration_settings.dart';

class IntegrationSettingsScreen extends StatefulWidget {
  const IntegrationSettingsScreen({super.key});

  @override
  State<IntegrationSettingsScreen> createState() => _IntegrationSettingsScreenState();
}

class _IntegrationSettingsScreenState extends State<IntegrationSettingsScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _twilioSidController = TextEditingController();
  final TextEditingController _twilioAuthController = TextEditingController();
  final TextEditingController _twilioPhoneController = TextEditingController();
  final TextEditingController _twilioMessagingServiceController =
      TextEditingController();
  final TextEditingController _openAiKeyController = TextEditingController();
  final TextEditingController _openAiOrgController = TextEditingController();
  final TextEditingController _openAiBaseUrlController = TextEditingController();
  final TextEditingController _otherIntegrationsController = TextEditingController();
  bool _enableSandbox = false;
  bool _twilioAuthConfigured = false;
  bool _openAiKeyConfigured = false;
  bool _hasHydrated = false;
  IntegrationSettings? _initialSettings;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadSettings();
    });
  }

  @override
  void dispose() {
    _twilioSidController.dispose();
    _twilioAuthController.dispose();
    _twilioPhoneController.dispose();
    _twilioMessagingServiceController.dispose();
    _openAiKeyController.dispose();
    _openAiOrgController.dispose();
    _openAiBaseUrlController.dispose();
    _otherIntegrationsController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0B141A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF111B21),
        foregroundColor: const Color(0xFFE9EDEF),
        title: const Text('Integration tokens'),
      ),
      body: SafeArea(
        child: Consumer<IntegrationSettingsController>(
          builder: (context, controller, _) {
            final isLoading = controller.isLoading && !_hasHydrated;
            final isSaving = controller.isSaving;
            final hasError = controller.error != null && !_hasHydrated;
            final ready = controller.settings?.ready ?? false;
            final isPriming =
                !_hasHydrated && controller.settings == null && controller.error == null;

            if (_hasHydrated && controller.settings != null) {
              _initialSettings = controller.settings;
            }

            if (isPriming || isLoading) {
              return const Center(
                child: CircularProgressIndicator(),
              );
            }

            if (hasError) {
              return _ErrorState(onRetry: _loadSettings);
            }

            return Form(
              key: _formKey,
              child: ListView(
                padding: const EdgeInsets.all(24),
                children: [
                  Row(
                    children: [
                      Icon(
                        ready ? Icons.verified_rounded : Icons.info_outline_rounded,
                        color: ready ? const Color(0xFF34D399) : const Color(0xFFF59E0B),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          ready
                              ? 'Twilio and OpenAI are connected. You can rotate tokens any time.'
                              : 'Securely store the credentials your workspace needs to connect to messaging and AI providers.',
                          style: const TextStyle(color: Color(0xFF8696A0), height: 1.4),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  _SettingsSection(
                    title: 'Twilio credentials',
                    children: [
                      _TokenField(
                        controller: _twilioSidController,
                        label: 'Account SID',
                        hint: 'ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX',
                        validator: _requiredValidator,
                      ),
                      const SizedBox(height: 16),
                      _TokenField(
                        controller: _twilioAuthController,
                        label: 'Auth token',
                        hint: _twilioAuthConfigured
                            ? 'Token already stored — enter to rotate'
                            : 'Your secret auth token',
                        helperText: _twilioAuthConfigured
                            ? 'A token is already saved for this workspace. Leave blank to keep it.'
                            : null,
                        obscureText: true,
                        validator: _requiredIfMissing(_twilioAuthConfigured),
                      ),
                      const SizedBox(height: 16),
                      _TokenField(
                        controller: _twilioPhoneController,
                        label: 'Messaging phone number',
                        hint: '+1 (555) 010-1234',
                      ),
                      const SizedBox(height: 16),
                      _TokenField(
                        controller: _twilioMessagingServiceController,
                        label: 'Messaging Service SID',
                        hint: 'MGXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX',
                        helperText:
                            'Found in Twilio Console → Messaging → Services. Use this when sending from a branded WhatsApp sender.',
                      ),
                      const SizedBox(height: 12),
                      SwitchListTile.adaptive(
                        value: _enableSandbox,
                        onChanged: (value) {
                          setState(() {
                            _enableSandbox = value;
                          });
                        },
                        title: const Text(
                          'Use Twilio sandbox mode',
                          style: TextStyle(color: Color(0xFFE9EDEF)),
                        ),
                        subtitle: const Text(
                          'Send messages through test credentials before going live.',
                          style: TextStyle(color: Color(0xFF8696A0), fontSize: 12),
                        ),
                        activeColor: const Color(0xFF00A884),
                        contentPadding: EdgeInsets.zero,
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  _SettingsSection(
                    title: 'OpenAI access',
                    children: [
                      _TokenField(
                        controller: _openAiKeyController,
                        label: 'API key',
                        hint: _openAiKeyConfigured
                            ? 'Key already stored — enter to rotate'
                            : 'sk-...your key...',
                        helperText: _openAiKeyConfigured
                            ? 'An API key is already stored. Leave blank to keep the existing one.'
                            : null,
                        obscureText: true,
                        validator: _requiredIfMissing(_openAiKeyConfigured),
                      ),
                      const SizedBox(height: 16),
                      _TokenField(
                        controller: _openAiOrgController,
                        label: 'Organization ID (optional)',
                        hint: 'org-...',
                      ),
                      const SizedBox(height: 16),
                      _TokenField(
                        controller: _openAiBaseUrlController,
                        label: 'API base URL (optional)',
                        hint: 'https://api.openai.com/v1',
                        helperText:
                            'Set this when routing requests through Azure OpenAI or a proxy. Leave blank for default.',
                      ),
                      const SizedBox(height: 12),
                      const Text(
                        'Need help rotating keys? Visit platform.openai.com/account/api-keys.',
                        style: TextStyle(color: Color(0xFF8696A0), fontSize: 12),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  _SettingsSection(
                    title: 'Other integrations',
                    children: [
                      const Text(
                        'Track CRMs, payment providers, or marketing tools that power your automations.',
                        style: TextStyle(color: Color(0xFF8696A0), height: 1.4),
                      ),
                      const SizedBox(height: 16),
                      _TokenField(
                        controller: _otherIntegrationsController,
                        label: 'Additional notes or tokens',
                        hint: 'Zapier key, CRM webhook, Slack bot token, etc.',
                        maxLines: 3,
                      ),
                      const SizedBox(height: 12),
                      Wrap(
                        spacing: 12,
                        runSpacing: 12,
                        children: const [
                          _IntegrationChip(label: 'Stripe'),
                          _IntegrationChip(label: 'HubSpot'),
                          _IntegrationChip(label: 'Salesforce'),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  ElevatedButton.icon(
                    onPressed: isSaving ? null : _save,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF00A884),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                    icon: isSaving
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.lock_rounded),
                    label: Text(isSaving ? 'Saving…' : 'Save credentials'),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Future<void> _loadSettings() async {
    try {
      final controller = context.read<IntegrationSettingsController>();
      final settings = await controller.load();
      if (!mounted) return;
      _applySettings(settings);
    } catch (_) {
      if (!mounted) return;
      _showMessage('Unable to load integration settings. Please try again.');
    }
  }

  void _applySettings(IntegrationSettings? settings) {
    if (settings == null) return;
    setState(() {
      _initialSettings = settings;
      _twilioAuthConfigured = settings.twilio?.authTokenConfigured ?? false;
      _openAiKeyConfigured = settings.openAi?.apiKeyConfigured ?? false;
      _twilioSidController.text = settings.twilio?.accountSid ?? '';
      _twilioAuthController.clear();
      _twilioPhoneController.text = settings.twilio?.whatsappFrom ?? '';
      _twilioMessagingServiceController.text = settings.twilio?.messagingServiceSid ?? '';
      _enableSandbox = settings.twilio?.sandboxMode ?? false;
      _openAiKeyController.clear();
      _openAiOrgController.text = settings.openAi?.organizationId ?? '';
      _openAiBaseUrlController.text = settings.openAi?.baseUrl ?? '';
      _otherIntegrationsController.text = settings.otherNotes ?? '';
      _hasHydrated = true;
    });
  }

  FormFieldValidator<String> _requiredIfMissing(bool alreadyConfigured) {
    return (value) {
      if (alreadyConfigured) return null;
      return _requiredValidator(value);
    };
  }

  String? _requiredValidator(String? value) {
    if (value == null || value.trim().isEmpty) {
      return 'This field is required.';
    }
    return null;
  }

  bool _didChange(String value, String? previous) => value.trim() != (previous ?? '');

  TwilioIntegrationUpdate? _buildTwilioUpdate() {
    final initial = _initialSettings?.twilio;
    final accountSid = _twilioSidController.text.trim();
    final authToken = _twilioAuthController.text.trim();
    final whatsappFrom = _twilioPhoneController.text.trim();
    final messagingServiceSid = _twilioMessagingServiceController.text.trim();

    final accountChanged = _didChange(accountSid, initial?.accountSid);
    final whatsappChanged = _didChange(whatsappFrom, initial?.whatsappFrom);
    final messagingServiceChanged =
        _didChange(messagingServiceSid, initial?.messagingServiceSid);
    final sandboxChanged = _enableSandbox != (initial?.sandboxMode ?? false);
    final authProvided = authToken.isNotEmpty;

    if (!(accountChanged || whatsappChanged || messagingServiceChanged || sandboxChanged || authProvided)) {
      return null;
    }

    return TwilioIntegrationUpdate(
      accountSid: accountChanged ? accountSid : null,
      authToken: authProvided ? authToken : null,
      messagingServiceSid: messagingServiceChanged ? messagingServiceSid : null,
      whatsappFrom: whatsappChanged ? whatsappFrom : null,
      sandboxMode: sandboxChanged ? _enableSandbox : null,
    );
  }

  OpenAiIntegrationUpdate? _buildOpenAiUpdate() {
    final initial = _initialSettings?.openAi;
    final apiKey = _openAiKeyController.text.trim();
    final orgId = _openAiOrgController.text.trim();
    final baseUrl = _openAiBaseUrlController.text.trim();

    final apiKeyProvided = apiKey.isNotEmpty;
    final orgChanged = _didChange(orgId, initial?.organizationId);
    final baseUrlChanged = _didChange(baseUrl, initial?.baseUrl);

    if (!(apiKeyProvided || orgChanged || baseUrlChanged)) {
      return null;
    }

    return OpenAiIntegrationUpdate(
      apiKey: apiKeyProvided ? apiKey : null,
      organizationId: orgChanged ? orgId : null,
      baseUrl: baseUrlChanged ? baseUrl : null,
    );
  }

  String? _buildOtherNotesUpdate() {
    final initial = _initialSettings?.otherNotes ?? '';
    final value = _otherIntegrationsController.text.trim();
    if (value == initial) return null;
    return value;
  }

  void _clearSensitiveFields() {
    _twilioAuthController.clear();
    _openAiKeyController.clear();
  }

  Future<void> _save() async {
    final isValid = _formKey.currentState?.validate() ?? false;
    if (!isValid) return;

    final twilioUpdate = _buildTwilioUpdate();
    final openAiUpdate = _buildOpenAiUpdate();
    final otherNotesUpdate = _buildOtherNotesUpdate();
    if (twilioUpdate == null && openAiUpdate == null && otherNotesUpdate == null) {
      _showMessage('No changes to save.');
      return;
    }

    FocusScope.of(context).unfocus();
    final controller = context.read<IntegrationSettingsController>();
    try {
      final updatedSettings = await controller.save(
        IntegrationSettingsUpdate(
          twilio: twilioUpdate,
          openAi: openAiUpdate,
          otherNotes: otherNotesUpdate,
        ),
      );
      if (!mounted) return;
      _applySettings(updatedSettings);
      _clearSensitiveFields();
      _showMessage('Credentials encrypted and stored for this workspace.');
    } catch (err) {
      if (!mounted) return;
      _showMessage('Failed to save credentials: $err');
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: const Color(0xFF1F2C34),
        content: Text(message),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, color: Color(0xFFF59E0B), size: 48),
          const SizedBox(height: 12),
          const Text(
            'Unable to load integration settings.',
            style: TextStyle(color: Color(0xFFE9EDEF), fontSize: 16),
          ),
          const SizedBox(height: 8),
          const Text(
            'Check your connection or refresh your login, then try again.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Color(0xFF8696A0)),
          ),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Retry'),
          ),
        ],
      ),
    );
  }
}

class _SettingsSection extends StatelessWidget {
  const _SettingsSection({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF111B21),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0x33243038)),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: Color(0xFFE9EDEF),
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 16),
          ...children,
        ],
      ),
    );
  }
}

class _TokenField extends StatelessWidget {
  const _TokenField({
    required this.controller,
    required this.label,
    this.hint,
    this.helperText,
    this.obscureText = false,
    this.maxLines = 1,
    this.validator,
  });

  final TextEditingController controller;
  final String label;
  final String? hint;
  final String? helperText;
  final bool obscureText;
  final int maxLines;
  final FormFieldValidator<String>? validator;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      obscureText: obscureText,
      maxLines: maxLines,
      validator: validator,
      style: const TextStyle(color: Color(0xFFE9EDEF)),
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        helperText: helperText,
        helperMaxLines: helperText != null ? 3 : null,
      ),
    );
  }
}

class _IntegrationChip extends StatelessWidget {
  const _IntegrationChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF1F2C34),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0x332FC6B2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.extension_rounded, color: Color(0xFF00A884), size: 16),
          const SizedBox(width: 6),
          Text(
            label,
            style: const TextStyle(color: Color(0xFFE9EDEF), fontSize: 12),
          ),
        ],
      ),
    );
  }
}
