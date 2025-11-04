import 'package:flutter/material.dart';

class AvatarCircle extends StatelessWidget {
  const AvatarCircle({
    required this.label,
    this.size = 48,
    this.image,
    super.key,
  });

  final String label;
  final double size;
  final ImageProvider<Object>? image;

  @override
  Widget build(BuildContext context) {
    if (image != null) {
      return SizedBox(
        width: size,
        height: size,
        child: ClipOval(
          child: Image(
            image: image!,
            fit: BoxFit.cover,
            loadingBuilder: (context, child, loadingProgress) {
              if (loadingProgress == null) return child;
              return _InitialsCircle(label: label, size: size);
            },
            errorBuilder: (context, error, stackTrace) => _InitialsCircle(
              label: label,
              size: size,
            ),
          ),
        ),
      );
    }

    return _InitialsCircle(label: label, size: size);
  }
}

class _InitialsCircle extends StatelessWidget {
  const _InitialsCircle({required this.label, required this.size});

  final String label;
  final double size;

  @override
  Widget build(BuildContext context) {
    final colors = _gradientFor(label);
    final textStyle = Theme.of(context).textTheme.titleMedium?.copyWith(
              color: Colors.white,
              fontWeight: FontWeight.w700,
            ) ??
        const TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.w700,
          fontSize: 18,
        );
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: LinearGradient(
          colors: colors,
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      alignment: Alignment.center,
      child: Text(
        _initials(label),
        style: textStyle,
      ),
    );
  }

  List<Color> _gradientFor(String value) {
    final palette = [
      [const Color(0xFF246BFD), const Color(0xFF4CC9F0)],
      [const Color(0xFF43AA8B), const Color(0xFF90BE6D)],
      [const Color(0xFFF94144), const Color(0xFFF3722C)],
      [const Color(0xFFF8961E), const Color(0xFFF9844A)],
      [const Color(0xFF9D4EDD), const Color(0xFF4895EF)],
    ];
    final index = value.isEmpty ? 0 : value.codeUnitAt(0) % palette.length;
    return palette[index];
  }

  String _initials(String name) {
    if (name.trim().isEmpty) return '?';
    final parts = name.trim().split(' ');
    final first = parts[0].isNotEmpty ? parts[0][0] : '?';
    if (parts.length == 1) {
      return first.toUpperCase();
    }
    final second = parts[1].isNotEmpty ? parts[1][0] : '';
    return (first + second).toUpperCase();
  }
}
