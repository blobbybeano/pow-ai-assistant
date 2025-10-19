import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

ThemeData buildPowWashTheme() {
  const background = Color(0xFF0B141A);
  const surface = Color(0xFF111B21);
  const surfaceAlt = Color(0xFF202C33);
  const accent = Color(0xFF00A884);
  const textPrimary = Color(0xFFE9EDEF);
  const textMuted = Color(0xFF8696A0);

  final colorScheme = ColorScheme.fromSeed(
    seedColor: accent,
    brightness: Brightness.dark,
    background: background,
    surface: surface,
  ).copyWith(
    primary: accent,
    onPrimary: Colors.white,
    secondary: const Color(0xFF008068),
    onSecondary: Colors.white,
    outline: const Color(0x338696A0),
    surfaceContainerLowest: surfaceAlt,
    error: const Color(0xFFF15C6D),
    onError: Colors.white,
  );

  final base = ThemeData(
    useMaterial3: true,
    colorScheme: colorScheme,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: background,
    canvasColor: background,
  );

  final textTheme = GoogleFonts.interTextTheme(base.textTheme).apply(
    bodyColor: textPrimary,
    displayColor: textPrimary,
  ).copyWith(
    titleLarge: GoogleFonts.inter(
      fontWeight: FontWeight.w700,
      fontSize: 22,
      color: textPrimary,
    ),
    bodyMedium: GoogleFonts.inter(
      fontSize: 15,
      color: textPrimary,
    ),
    bodySmall: GoogleFonts.inter(
      fontSize: 13,
      color: textMuted,
    ),
  );

  return base.copyWith(
    textTheme: textTheme,
    appBarTheme: AppBarTheme(
      backgroundColor: surface,
      foregroundColor: textPrimary,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: GoogleFonts.inter(
        fontSize: 20,
        fontWeight: FontWeight.w600,
        color: textPrimary,
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: accent,
        foregroundColor: Colors.white,
        textStyle: GoogleFonts.inter(fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: textPrimary,
        side: const BorderSide(color: Color(0x338696A0)),
        textStyle: GoogleFonts.inter(fontWeight: FontWeight.w600),
      ),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: MaterialStateProperty.resolveWith((states) {
        if (states.contains(MaterialState.selected)) return accent;
        return const Color(0xFFE9EDEF);
      }),
      trackColor: MaterialStateProperty.resolveWith((states) {
        if (states.contains(MaterialState.selected)) return accent.withOpacity(0.4);
        return const Color(0x338696A0);
      }),
    ),
    dividerColor: const Color(0x338696A0),
    dialogBackgroundColor: surface,
    cardColor: surfaceAlt,
  );
}
