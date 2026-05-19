import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

// ── Palette ──────────────────────────────────────────────────
const kBg        = Color(0xFF070C1B);
const kSurface   = Color(0xFF0D1628);
const kCard      = Color(0xFF111E35);
const kCardHover = Color(0xFF162440);
const kBorder    = Color(0xFF1D2E4A);
const kBorderDim = Color(0xFF0F1E36);

const kPrimary    = Color(0xFF4A7FFF);
const kPrimaryDim = Color(0xFF1A2D5C);
const kPrimaryLit = Color(0xFF7AABFF);
const kAccent     = Color(0xFF00D4FF);
const kAccentDim  = Color(0xFF00364A);

const kTextPrimary   = Color(0xFFEDF2FF);
const kTextSecondary = Color(0xFF7A91BE);
const kTextDim       = Color(0xFF4A5A7B);

const kSuccess = Color(0xFF22C55E);
const kError   = Color(0xFFF87171);
const kWarning = Color(0xFFFBBF24);

// ── Gradients ─────────────────────────────────────────────────
const kGradientBlue = LinearGradient(
  colors: [kPrimary, kAccent],
  begin: Alignment.centerLeft,
  end: Alignment.centerRight,
);

const kGradientSubtle = LinearGradient(
  colors: [Color(0xFF0D1628), Color(0xFF111E35)],
  begin: Alignment.topLeft,
  end: Alignment.bottomRight,
);

// ── Theme ─────────────────────────────────────────────────────
ThemeData buildAppTheme() {
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: kBg,
    colorScheme: const ColorScheme.dark(
      primary:                kPrimary,
      onPrimary:              Colors.white,
      primaryContainer:       kPrimaryDim,
      onPrimaryContainer:     kPrimaryLit,
      secondary:              kAccent,
      onSecondary:            kBg,
      secondaryContainer:     kAccentDim,
      onSecondaryContainer:   kAccent,
      surface:                kSurface,
      onSurface:              kTextPrimary,
      surfaceContainerHighest: kCard,
      outline:                kBorder,
      outlineVariant:         kBorderDim,
      error:                  kError,
      onError:                Colors.white,
      tertiary:               kSuccess,
      onTertiary:             Colors.white,
    ),

    // Cards
    cardTheme: CardThemeData(
      color: kCard,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: kBorder, width: 1),
      ),
    ),

    // AppBar
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      foregroundColor: kTextPrimary,
      systemOverlayStyle: SystemUiOverlayStyle(
        statusBarBrightness: Brightness.dark,
        statusBarIconBrightness: Brightness.light,
      ),
      titleTextStyle: TextStyle(
        color: kTextPrimary,
        fontSize: 18,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.3,
      ),
      iconTheme: IconThemeData(color: kTextSecondary),
      actionsIconTheme: IconThemeData(color: kTextSecondary),
    ),

    // Inputs
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: kSurface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: kBorder),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: kBorder),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: kPrimary, width: 1.5),
      ),
      labelStyle: const TextStyle(color: kTextSecondary, fontSize: 14),
      hintStyle: const TextStyle(color: kTextDim, fontSize: 14),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),

    // Typography
    textTheme: const TextTheme(
      displayLarge:  TextStyle(color: kTextPrimary,   fontSize: 32, fontWeight: FontWeight.w800, letterSpacing: -1.0),
      displayMedium: TextStyle(color: kTextPrimary,   fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -0.5),
      titleLarge:    TextStyle(color: kTextPrimary,   fontSize: 20, fontWeight: FontWeight.w700, letterSpacing: -0.3),
      titleMedium:   TextStyle(color: kTextPrimary,   fontSize: 16, fontWeight: FontWeight.w600),
      titleSmall:    TextStyle(color: kTextSecondary, fontSize: 12, fontWeight: FontWeight.w600, letterSpacing: 0.8),
      bodyLarge:     TextStyle(color: kTextPrimary,   fontSize: 16, height: 1.55),
      bodyMedium:    TextStyle(color: kTextPrimary,   fontSize: 14, height: 1.5),
      bodySmall:     TextStyle(color: kTextSecondary, fontSize: 12, height: 1.4),
      labelLarge:    TextStyle(color: kTextPrimary,   fontSize: 15, fontWeight: FontWeight.w600, letterSpacing: 0.1),
      labelMedium:   TextStyle(color: kTextSecondary, fontSize: 13, fontWeight: FontWeight.w500),
      labelSmall:    TextStyle(color: kTextSecondary, fontSize: 11, fontWeight: FontWeight.w500, letterSpacing: 0.5),
    ),

    dividerTheme: const DividerThemeData(color: kBorder, space: 1, thickness: 1),

    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? Colors.white : kTextSecondary,
      ),
      trackColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? kPrimary : kCard,
      ),
      trackOutlineColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? Colors.transparent : kBorder,
      ),
    ),

    sliderTheme: SliderThemeData(
      activeTrackColor: kPrimary,
      inactiveTrackColor: kCard,
      thumbColor: kPrimary,
      overlayColor: kPrimary.withOpacity(0.15),
      trackHeight: 3,
      thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 8),
    ),

    chipTheme: ChipThemeData(
      backgroundColor: kCard,
      side: const BorderSide(color: kBorder),
      labelStyle: const TextStyle(color: kTextPrimary, fontSize: 13),
      padding: const EdgeInsets.symmetric(horizontal: 4),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      deleteIconColor: kTextSecondary,
    ),

    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: kSurface,
      surfaceTintColor: Colors.transparent,
      shadowColor: Colors.transparent,
      indicatorColor: kPrimaryDim,
      labelTextStyle: WidgetStateProperty.resolveWith((s) {
        if (s.contains(WidgetState.selected)) {
          return const TextStyle(color: kPrimaryLit, fontSize: 11, fontWeight: FontWeight.w600);
        }
        return const TextStyle(color: kTextSecondary, fontSize: 11);
      }),
      iconTheme: WidgetStateProperty.resolveWith((s) {
        if (s.contains(WidgetState.selected)) {
          return const IconThemeData(color: kPrimaryLit, size: 22);
        }
        return const IconThemeData(color: kTextSecondary, size: 22);
      }),
    ),

    snackBarTheme: SnackBarThemeData(
      backgroundColor: kCard,
      contentTextStyle: const TextStyle(color: kTextPrimary, fontSize: 14),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: kBorder),
      ),
      behavior: SnackBarBehavior.floating,
    ),

    dialogTheme: DialogThemeData(
      backgroundColor: kSurface,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: const TextStyle(
        color: kTextPrimary, fontSize: 18, fontWeight: FontWeight.w700, letterSpacing: -0.2,
      ),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: kBorder),
      ),
    ),
  );
}
