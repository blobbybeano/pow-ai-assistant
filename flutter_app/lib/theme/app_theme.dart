import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

ThemeData buildPowWashTheme() {
  final colorScheme = ColorScheme.fromSeed(
    seedColor: const Color(0xFF246BFD),
    brightness: Brightness.light,
  ).copyWith(
    background: const Color(0xFFF5F7FA),
    surface: Colors.white,
  );

  final baseTextTheme = GoogleFonts.interTextTheme(
    ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
    ).textTheme,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: colorScheme,
    textTheme: baseTextTheme.copyWith(
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
      color: colorScheme.surface,
      surfaceTintColor: Colors.transparent,
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
      ),
      elevation: 0,
      clipBehavior: Clip.antiAlias,
    ),
    chipTheme: ChipThemeData(
      side: const WidgetStatePropertyAll(BorderSide(style: BorderStyle.none)),
      shape: const WidgetStatePropertyAll(StadiumBorder()),
      padding: const WidgetStatePropertyAll(
        EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      ),
      labelStyle: WidgetStatePropertyAll(
        GoogleFonts.inter(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          color: colorScheme.onPrimaryContainer,
        ),
      ),
      color: WidgetStatePropertyAll(colorScheme.primaryContainer),
    ),
  );
}
