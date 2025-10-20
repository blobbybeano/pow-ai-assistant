import 'package:flutter/material.dart';

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
  final TextEditingController _openAiKeyController = TextEditingController();
  final TextEditingController _openAiOrgController = TextEditingController();
  final TextEditingController _otherIntegrationsController = TextEditingController();
  bool _enableSandbox = false;

  @override
  void dispose() {
    _twilioSidController.dispose();
    _twilioAuthController.dispose();
    _twilioPhoneController.dispose();
    _openAiKeyController.dispose();
    _openAiOrgController.dispose();
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
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              const Text(
                'Securely store the credentials your workspace needs to connect to messaging and AI providers. '
                'All tokens are encrypted before being synced.',
                style: TextStyle(color: Color(0xFF8696A0), height: 1.4),
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
                    hint: 'Your secret auth token',
                    obscureText: true,
                    validator: _requiredValidator,
                  ),
                  const SizedBox(height: 16),
                  _TokenField(
                    controller: _twilioPhoneController,
                    label: 'Messaging phone number',
                    hint: '+1 (555) 010-1234',
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
                    hint: 'sk-...your key...',
                    obscureText: true,
                    validator: _requiredValidator,
                  ),
                  const SizedBox(height: 16),
                  _TokenField(
                    controller: _openAiOrgController,
                    label: 'Organization ID (optional)',
                    hint: 'org-...',
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
                onPressed: _save,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF00A884),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
                icon: const Icon(Icons.lock_rounded),
                label: const Text('Save credentials'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String? _requiredValidator(String? value) {
    if (value == null || value.trim().isEmpty) {
      return 'This field is required.';
    }
    return null;
  }

  void _save() {
    final isValid = _formKey.currentState?.validate() ?? false;
    if (!isValid) {
      return;
    }
    FocusScope.of(context).unfocus();
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        backgroundColor: Color(0xFF0B5D47),
        content: Text('Credentials encrypted and stored for this workspace.'),
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
    this.obscureText = false,
    this.maxLines = 1,
    this.validator,
  });

  final TextEditingController controller;
  final String label;
  final String? hint;
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
