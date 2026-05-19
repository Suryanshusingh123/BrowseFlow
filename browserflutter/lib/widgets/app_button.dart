import 'package:flutter/material.dart';
import '../core/theme.dart';

class AppButton extends StatelessWidget {
  final String label;
  final IconData? icon;
  final VoidCallback? onPressed;
  final bool loading;
  final bool outlined;
  final bool small;

  const AppButton({
    super.key,
    required this.label,
    this.icon,
    this.onPressed,
    this.loading = false,
    this.outlined = false,
    this.small = false,
  });

  @override
  Widget build(BuildContext context) {
    final height = small ? 40.0 : 52.0;
    final fontSize = small ? 13.0 : 15.0;
    final radius = small ? 10.0 : 14.0;

    if (outlined) {
      return SizedBox(
        height: height,
        child: OutlinedButton(
          onPressed: onPressed,
          style: OutlinedButton.styleFrom(
            foregroundColor: kPrimary,
            side: const BorderSide(color: kBorder, width: 1),
            backgroundColor: kCard,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius)),
            padding: const EdgeInsets.symmetric(horizontal: 20),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) ...[Icon(icon, size: 16, color: kTextSecondary), const SizedBox(width: 6)],
              Text(label, style: TextStyle(fontSize: fontSize, color: kTextSecondary, fontWeight: FontWeight.w500)),
            ],
          ),
        ),
      );
    }

    final enabled = onPressed != null && !loading;

    return Container(
      height: height,
      decoration: BoxDecoration(
        gradient: enabled ? kGradientBlue : null,
        color: enabled ? null : kCard,
        borderRadius: BorderRadius.circular(radius),
        border: enabled ? null : Border.all(color: kBorder),
        boxShadow: enabled
            ? [
                BoxShadow(
                  color: kPrimary.withOpacity(0.30),
                  blurRadius: 20,
                  spreadRadius: -4,
                  offset: const Offset(0, 8),
                ),
              ]
            : null,
      ),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(radius),
        child: InkWell(
          onTap: enabled ? onPressed : null,
          borderRadius: BorderRadius.circular(radius),
          splashColor: Colors.white.withOpacity(0.1),
          highlightColor: Colors.transparent,
          child: Center(
            child: loading
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  )
                : Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (icon != null) ...[
                        Icon(icon, size: small ? 16 : 18, color: Colors.white),
                        const SizedBox(width: 8),
                      ],
                      Text(
                        label,
                        style: TextStyle(
                          color: enabled ? Colors.white : kTextDim,
                          fontSize: fontSize,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.1,
                        ),
                      ),
                    ],
                  ),
          ),
        ),
      ),
    );
  }
}
