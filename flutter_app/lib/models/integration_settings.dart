class TwilioIntegrationSettings {
  const TwilioIntegrationSettings({
    this.accountSid,
    this.messagingServiceSid,
    this.whatsappFrom,
    this.sandboxMode = false,
    this.authTokenConfigured = false,
  });

  factory TwilioIntegrationSettings.fromJson(Map<String, dynamic> json) {
    return TwilioIntegrationSettings(
      accountSid: (json['accountSid'] as String?)?.trim(),
      messagingServiceSid: (json['messagingServiceSid'] as String?)?.trim(),
      whatsappFrom: (json['whatsappFrom'] as String?)?.trim(),
      sandboxMode: json['sandboxMode'] == true,
      authTokenConfigured: json['authTokenConfigured'] == true,
    );
  }

  final String? accountSid;
  final String? messagingServiceSid;
  final String? whatsappFrom;
  final bool sandboxMode;
  final bool authTokenConfigured;

  bool get hasCredentials =>
      (accountSid != null && accountSid!.isNotEmpty) && authTokenConfigured;
}

class OpenAiIntegrationSettings {
  const OpenAiIntegrationSettings({
    this.organizationId,
    this.baseUrl,
    this.apiKeyConfigured = false,
  });

  factory OpenAiIntegrationSettings.fromJson(Map<String, dynamic> json) {
    return OpenAiIntegrationSettings(
      organizationId: (json['organizationId'] as String?)?.trim(),
      baseUrl: (json['baseUrl'] as String?)?.trim(),
      apiKeyConfigured: json['apiKeyConfigured'] == true,
    );
  }

  final String? organizationId;
  final String? baseUrl;
  final bool apiKeyConfigured;
}

class IntegrationSettings {
  const IntegrationSettings({
    this.twilio,
    this.openAi,
    this.otherNotes,
    this.ready = false,
  });

  factory IntegrationSettings.fromJson(Map<String, dynamic> json) {
    final twilioJson = json['twilio'];
    final openAiJson = json['openAi'];
    return IntegrationSettings(
      ready: json['ready'] == true,
      twilio: twilioJson is Map<String, dynamic>
          ? TwilioIntegrationSettings.fromJson(twilioJson)
          : null,
      openAi: openAiJson is Map<String, dynamic>
          ? OpenAiIntegrationSettings.fromJson(openAiJson)
          : null,
      otherNotes: (json['otherNotes'] as String?)?.trim(),
    );
  }

  final TwilioIntegrationSettings? twilio;
  final OpenAiIntegrationSettings? openAi;
  final String? otherNotes;
  final bool ready;
}

class IntegrationSettingsUpdate {
  const IntegrationSettingsUpdate({
    this.twilio,
    this.openAi,
    this.otherNotes,
  });

  final TwilioIntegrationUpdate? twilio;
  final OpenAiIntegrationUpdate? openAi;
  final String? otherNotes;

  Map<String, dynamic> toJson() {
    return {
      if (twilio != null) 'twilio': twilio!.toJson(),
      if (openAi != null) 'openAi': openAi!.toJson(),
      if (otherNotes != null) 'otherNotes': otherNotes,
    };
  }
}

class TwilioIntegrationUpdate {
  const TwilioIntegrationUpdate({
    this.accountSid,
    this.authToken,
    this.messagingServiceSid,
    this.whatsappFrom,
    this.sandboxMode,
  });

  final String? accountSid;
  final String? authToken;
  final String? messagingServiceSid;
  final String? whatsappFrom;
  final bool? sandboxMode;

  Map<String, dynamic> toJson() {
    return {
      if (accountSid != null) 'accountSid': accountSid,
      if (authToken != null) 'authToken': authToken,
      if (messagingServiceSid != null) 'messagingServiceSid': messagingServiceSid,
      if (whatsappFrom != null) 'whatsappFrom': whatsappFrom,
      if (sandboxMode != null) 'sandboxMode': sandboxMode,
    };
  }
}

class OpenAiIntegrationUpdate {
  const OpenAiIntegrationUpdate({
    this.apiKey,
    this.organizationId,
    this.baseUrl,
  });

  final String? apiKey;
  final String? organizationId;
  final String? baseUrl;

  Map<String, dynamic> toJson() {
    return {
      if (apiKey != null) 'apiKey': apiKey,
      if (organizationId != null) 'organizationId': organizationId,
      if (baseUrl != null) 'baseUrl': baseUrl,
    };
  }
}
