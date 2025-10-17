import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

ThemeData buildPowWashTheme() {
  final base = ThemeData.light(useMaterial3: true);
  final colorScheme = ColorScheme.fromSeed(seedColor: const Color(0xFF246BFD));

  return base.copyWith(
    colorScheme: colorScheme,
    textTheme: GoogleFonts.interTextTheme(base.textTheme).copyWith(
      titleLarge: GoogleFonts.inter(
        fontWeight: FontWeight.w700,
        fontSize: 22,
        color: colorScheme.onBackground,
      ),
      bodyMedium: GoogleFonts.inter(
        fontSize: 15,
        color: const Color(0xFF1D1E20),
      ),
    ),
    scaffoldBackgroundColor: const Color(0xFFF5F7FA),
    appBarTheme: AppBarTheme(
      backgroundColor: colorScheme.surface,
      foregroundColor: colorScheme.onSurface,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: GoogleFonts.inter(
        fontSize: 20,
        fontWeight: FontWeight.w600,
        color: colorScheme.onSurface,
      ),
    ),
    cardTheme: CardThemeData(
      color: Colors.white,
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
      ),
      elevation: 0,
    ),
    chipTheme: ChipThemeData(
      backgroundColor: colorScheme.primaryContainer,
      labelStyle: GoogleFonts.inter(
        fontSize: 13,
        fontWeight: FontWeight.w600,
        color: colorScheme.onPrimaryContainer,
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
    ),
  );
}
