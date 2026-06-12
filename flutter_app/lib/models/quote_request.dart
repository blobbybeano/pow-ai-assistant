class QuoteRequest {
  QuoteRequest({
    required this.id,
    required this.convId,
    required this.description,
    required this.customerMsg,
    required this.images,
    required this.createdAt,
    required this.status,
    this.advice,
    this.answeredAt,
  });

  factory QuoteRequest.fromJson(Map<String, dynamic> json) {
    final rawImages = json['images'] as List<dynamic>? ?? [];
    return QuoteRequest(
      id: json['id'] as String,
      convId: json['conv_id'] as String,
      description: json['description'] as String? ?? '',
      customerMsg: json['customer_msg'] as String? ?? '',
      images: rawImages
          .map((e) => QuoteImage.fromJson(e as Map<String, dynamic>))
          .toList(),
      createdAt: DateTime.fromMillisecondsSinceEpoch(
        ((json['created_at'] as num) * 1000).round(),
      ),
      status: json['status'] as String? ?? 'pending',
      advice: json['advice'] as String?,
      answeredAt: json['answered_at'] != null
          ? DateTime.fromMillisecondsSinceEpoch(
              ((json['answered_at'] as num) * 1000).round(),
            )
          : null,
    );
  }

  final String id;
  final String convId;
  final String description;
  final String customerMsg;
  final List<QuoteImage> images;
  final DateTime createdAt;
  final String status;
  final String? advice;
  final DateTime? answeredAt;

  bool get isPending => status == 'pending';
}

class QuoteImage {
  QuoteImage({required this.data, required this.contentType});

  factory QuoteImage.fromJson(Map<String, dynamic> json) => QuoteImage(
        data: json['data'] as String,
        contentType: json['contentType'] as String? ?? 'image/jpeg',
      );

  final String data;
  final String contentType;
}
