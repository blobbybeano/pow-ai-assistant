class AppUser {
  const AppUser({
    required this.id,
    required this.displayName,
    this.email,
    this.avatarEmoji,
  });

  final String id;
  final String displayName;
  final String? email;
  final String? avatarEmoji;

  String get initials {
    if (avatarEmoji != null && avatarEmoji!.isNotEmpty) {
      return avatarEmoji!;
    }
    final cleaned = displayName.trim();
    if (cleaned.isEmpty) {
      return '?';
    }
    final parts = cleaned.split(RegExp(r'\s+')).where((part) => part.isNotEmpty).toList();
    String leading(String value) => value.isEmpty ? '' : value[0].toUpperCase();
    if (parts.length == 1) {
      return leading(parts.first);
    }
    return (leading(parts.first) + leading(parts.last)).trim();
  }

  AppUser copyWith({
    String? id,
    String? displayName,
    String? email,
    String? avatarEmoji,
  }) {
    return AppUser(
      id: id ?? this.id,
      displayName: displayName ?? this.displayName,
      email: email ?? this.email,
      avatarEmoji: avatarEmoji ?? this.avatarEmoji,
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is AppUser &&
        other.id == id &&
        other.displayName == displayName &&
        other.email == email &&
        other.avatarEmoji == avatarEmoji;
  }

  @override
  int get hashCode => Object.hash(id, displayName, email, avatarEmoji);
}
