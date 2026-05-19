import 'package:flutter/material.dart';
import '../core/api.dart';
import '../core/theme.dart';
import '../models/models.dart';
import '../widgets/app_button.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<CachedResultEntry> _entries = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final json = await ApiService.listResults();
      final raw = json['results'] as List? ?? [];
      setState(() {
        _entries = raw
            .map((e) => CachedResultEntry.fromJson(e as Map<String, dynamic>))
            .toList();
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _deleteEntry(CachedResultEntry entry) async {
    try {
      await ApiService.deleteResult(entry.goal);
      setState(() => _entries.remove(entry));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed: $e')),
        );
      }
    }
  }

  Future<void> _clearAll() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Clear all?'),
        content: const Text(
          'All cached agent results will be deleted.',
          style: TextStyle(color: kTextSecondary, fontSize: 14),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel', style: TextStyle(color: kTextSecondary)),
          ),
          Container(
            decoration: BoxDecoration(
              color: kError.withOpacity(0.12),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: kError.withOpacity(0.3)),
            ),
            child: TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              style: TextButton.styleFrom(foregroundColor: kError),
              child: const Text('Clear all', style: TextStyle(fontWeight: FontWeight.w600)),
            ),
          ),
        ],
      ),
    );
    if (confirm == true) {
      await ApiService.clearAllResults();
      setState(() => _entries.clear());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBg,
      body: CustomScrollView(
        slivers: [
          // Header
          SliverToBoxAdapter(
            child: SafeArea(
              bottom: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'History',
                            style: TextStyle(
                              color: kTextPrimary, fontSize: 28, fontWeight: FontWeight.w800,
                              letterSpacing: -0.8),
                          ),
                          SizedBox(height: 2),
                          Text(
                            'Cached agent results',
                            style: TextStyle(color: kTextSecondary, fontSize: 13),
                          ),
                        ],
                      ),
                    ),
                    Row(
                      children: [
                        if (_entries.isNotEmpty)
                          _IconBtn(icon: Icons.delete_sweep_outlined, onTap: _clearAll),
                        const SizedBox(width: 8),
                        _IconBtn(icon: Icons.refresh_rounded, onTap: _load),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),

          // Content
          if (_loading)
            const SliverFillRemaining(
              child: Center(child: CircularProgressIndicator(color: kPrimary, strokeWidth: 2)),
            )
          else if (_error != null)
            SliverFillRemaining(
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.all(32),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(_error!, style: const TextStyle(color: kTextSecondary, fontSize: 13)),
                      const SizedBox(height: 20),
                      AppButton(label: 'Retry', icon: Icons.refresh_rounded, onPressed: _load),
                    ],
                  ),
                ),
              ),
            )
          else if (_entries.isEmpty)
            SliverFillRemaining(
              child: Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Container(
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        color: kCard,
                        shape: BoxShape.circle,
                        border: Border.all(color: kBorder),
                      ),
                      child: const Icon(Icons.history_rounded, size: 32, color: kTextDim),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'No cached results',
                      style: TextStyle(
                        color: kTextPrimary, fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'Toggle "Use cache" on the Run screen\nbefore running the agent.',
                      style: TextStyle(color: kTextDim, fontSize: 13, height: 1.5),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            )
          else
            SliverList(
              delegate: SliverChildBuilderDelegate(
                (_, i) => _EntryCard(
                  entry: _entries[i],
                  onDelete: () => _deleteEntry(_entries[i]),
                ),
                childCount: _entries.length,
              ),
            ),

          const SliverToBoxAdapter(child: SizedBox(height: 80)),
        ],
      ),
    );
  }
}

class _IconBtn extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;

  const _IconBtn({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          color: kCard,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: kBorder),
        ),
        child: Icon(icon, size: 16, color: kTextSecondary),
      ),
    );
  }
}

class _EntryCard extends StatelessWidget {
  final CachedResultEntry entry;
  final VoidCallback onDelete;

  const _EntryCard({required this.entry, required this.onDelete});

  String get _ageLabel {
    final h = entry.ageHours;
    if (h < 1) return '${(h * 60).round()}m ago';
    if (h < 24) return '${h.round()}h ago';
    return '${(h / 24).round()}d ago';
  }

  Color get _ageColor {
    if (entry.ageHours < 1) return kSuccess;
    if (entry.ageHours < 6) return kAccent;
    return kTextDim;
  }

  @override
  Widget build(BuildContext context) {
    return Dismissible(
      key: ValueKey(entry.goal),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 5),
        decoration: BoxDecoration(
          color: kError.withOpacity(0.12),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: kError.withOpacity(0.25)),
        ),
        child: const Icon(Icons.delete_outline_rounded, color: kError, size: 20),
      ),
      onDismissed: (_) => onDelete(),
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 5),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: kCard,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: kBorder),
        ),
        child: Row(
          children: [
            // Item count badge
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: kSurface,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: kBorder),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    '${entry.itemCount}',
                    style: const TextStyle(
                      color: kPrimaryLit, fontSize: 14, fontWeight: FontWeight.w800,
                      fontFamily: 'Courier New',
                    ),
                  ),
                  const Text(
                    'items',
                    style: TextStyle(color: kTextDim, fontSize: 9, letterSpacing: 0.2),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),

            // Goal + age
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    entry.goal,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: kTextPrimary, fontSize: 13, fontWeight: FontWeight.w500, height: 1.4),
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Container(
                        width: 5, height: 5,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: _ageColor,
                        ),
                      ),
                      const SizedBox(width: 5),
                      Text(
                        _ageLabel,
                        style: TextStyle(
                          color: _ageColor, fontSize: 11, fontFamily: 'Courier New'),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            // Delete button
            GestureDetector(
              onTap: onDelete,
              child: const Padding(
                padding: EdgeInsets.all(4),
                child: Icon(Icons.close_rounded, size: 16, color: kTextDim),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
