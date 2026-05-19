import 'package:flutter/material.dart';
import '../core/theme.dart';

class ItemCard extends StatelessWidget {
  final Map<String, dynamic> item;
  final int index;

  const ItemCard({super.key, required this.item, required this.index});

  @override
  Widget build(BuildContext context) {
    final name = item['name']?.toString() ?? item['title']?.toString() ?? 'Item ${index + 1}';
    final price = item['price']?.toString();
    final rating = item['rating']?.toString();
    final otherKeys = item.keys.where((k) => !{'name', 'title', 'price', 'rating'}.contains(k));

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 5),
      decoration: BoxDecoration(
        color: kCard,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: kBorder, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Rank badge
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                gradient: index < 3 ? kGradientBlue : null,
                color: index >= 3 ? kSurface : null,
                borderRadius: BorderRadius.circular(8),
                border: index >= 3 ? Border.all(color: kBorder) : null,
              ),
              child: Center(
                child: Text(
                  '${index + 1}',
                  style: TextStyle(
                    color: index < 3 ? Colors.white : kTextDim,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    fontFamily: 'Courier New',
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            // Content
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    style: const TextStyle(
                      color: kTextPrimary,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      height: 1.35,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (price != null || rating != null) ...[
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        if (price != null)
                          _Badge(
                            label: price,
                            color: kAccent,
                            icon: Icons.currency_rupee_rounded,
                          ),
                        if (price != null && rating != null) const SizedBox(width: 8),
                        if (rating != null)
                          _Badge(
                            label: rating,
                            color: kWarning,
                            icon: Icons.star_rounded,
                          ),
                      ],
                    ),
                  ],
                  for (final key in otherKeys)
                    if (item[key] != null && item[key].toString().isNotEmpty) ...[
                      const SizedBox(height: 4),
                      RichText(
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        text: TextSpan(
                          children: [
                            TextSpan(
                              text: '$key  ',
                              style: const TextStyle(
                                color: kTextDim,
                                fontSize: 11,
                                fontWeight: FontWeight.w500,
                                letterSpacing: 0.3,
                                fontFamily: 'Courier New',
                              ),
                            ),
                            TextSpan(
                              text: item[key].toString(),
                              style: const TextStyle(color: kTextSecondary, fontSize: 12),
                            ),
                          ],
                        ),
                      ),
                    ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  final String label;
  final Color color;
  final IconData icon;

  const _Badge({required this.label, required this.color, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.10),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withOpacity(0.25), width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              color: color,
              fontWeight: FontWeight.w600,
              fontFamily: 'Courier New',
            ),
          ),
        ],
      ),
    );
  }
}
