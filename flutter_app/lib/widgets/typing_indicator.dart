import 'dart:math' as math;

import 'package:flutter/material.dart';

class TypingIndicator extends StatefulWidget {
  const TypingIndicator({super.key, this.dotColor = Colors.white, this.dotSize = 8});

  final Color dotColor;
  final double dotSize;

  @override
  State<TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<TypingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller =
        AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))
          ..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final dotSize = widget.dotSize;
    return SizedBox(
      width: dotSize * 4,
      height: dotSize * 1.5,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          return Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: List.generate(3, (index) {
              final phase = index / 3;
              final value = (_controller.value + phase) % 1.0;
              final wave = math.sin(value * math.pi);
              final opacity = 0.3 + 0.7 * wave;
              final effectiveOpacity = opacity.clamp(0.3, 1.0) as double;
              return Opacity(
                opacity: effectiveOpacity,
                child: Container(
                  width: dotSize,
                  height: dotSize,
                  decoration: BoxDecoration(
                    color: widget.dotColor,
                    shape: BoxShape.circle,
                  ),
                ),
              );
            }),
          );
        },
      ),
    );
  }
}
