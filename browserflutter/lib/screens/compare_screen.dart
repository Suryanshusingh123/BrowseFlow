import 'package:flutter/material.dart';
import '../core/api.dart';
import '../core/theme.dart';
import '../models/models.dart';
import '../widgets/item_card.dart';
import '../widgets/app_button.dart';

class CompareScreen extends StatefulWidget {
  const CompareScreen({super.key});

  @override
  State<CompareScreen> createState() => _CompareScreenState();
}

class _CompareScreenState extends State<CompareScreen> {
  final _queryController = TextEditingController();
  final _addSiteController = TextEditingController();

  final List<String> _sites = ['amazon.in', 'flipkart.com'];
  int _maxSteps = 12;
  bool _summarize = true;

  bool _loading = false;
  CompareResult? _result;
  String? _error;

  @override
  void dispose() {
    _queryController.dispose();
    _addSiteController.dispose();
    super.dispose();
  }

  Future<void> _run() async {
    final query = _queryController.text.trim();
    if (query.isEmpty || _sites.isEmpty) return;

    setState(() {
      _loading = true;
      _result = null;
      _error = null;
    });

    try {
      final json = await ApiService.compare(
        query: query,
        sites: _sites,
        maxSteps: _maxSteps,
        summarize: _summarize,
      );
      setState(() {
        _result = CompareResult.fromJson(json);
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  void _addSite(String site) {
    site = site.trim().toLowerCase();
    if (site.isNotEmpty && !_sites.contains(site)) {
      setState(() => _sites.add(site));
    }
    _addSiteController.clear();
  }

  void _reset() => setState(() {
        _result = null;
        _error = null;
      });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBg,
      body: AnimatedSwitcher(
        duration: const Duration(milliseconds: 300),
        child: _loading
            ? _LoadingView(key: const ValueKey('loading'), siteCount: _sites.length)
            : _result != null
                ? _ResultView(key: const ValueKey('result'), result: _result!, onReset: _reset)
                : _error != null
                    ? _ErrorView(key: const ValueKey('error'), error: _error!, onRetry: _reset)
                    : _InputView(
                        key: const ValueKey('input'),
                        queryController: _queryController,
                        addSiteController: _addSiteController,
                        sites: _sites,
                        maxSteps: _maxSteps,
                        summarize: _summarize,
                        onAddSite: _addSite,
                        onRemoveSite: (s) => setState(() => _sites.remove(s)),
                        onMaxStepsChanged: (v) => setState(() => _maxSteps = v),
                        onSummarizeChanged: (v) => setState(() => _summarize = v),
                        onRun: _run,
                      ),
      ),
    );
  }
}

// ── Input ─────────────────────────────────────────────────────

class _InputView extends StatelessWidget {
  final TextEditingController queryController;
  final TextEditingController addSiteController;
  final List<String> sites;
  final int maxSteps;
  final bool summarize;
  final ValueChanged<String> onAddSite;
  final ValueChanged<String> onRemoveSite;
  final ValueChanged<int> onMaxStepsChanged;
  final ValueChanged<bool> onSummarizeChanged;
  final VoidCallback onRun;

  const _InputView({
    super.key,
    required this.queryController,
    required this.addSiteController,
    required this.sites,
    required this.maxSteps,
    required this.summarize,
    required this.onAddSite,
    required this.onRemoveSite,
    required this.onMaxStepsChanged,
    required this.onSummarizeChanged,
    required this.onRun,
  });

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        SliverToBoxAdapter(
          child: SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Compare sites',
                    style: TextStyle(
                      color: kTextPrimary, fontSize: 28, fontWeight: FontWeight.w800, letterSpacing: -0.8),
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Search the same query across multiple sites simultaneously.',
                    style: TextStyle(color: kTextSecondary, fontSize: 14, height: 1.5),
                  ),
                  const SizedBox(height: 24),

                  // Query input
                  TextField(
                    controller: queryController,
                    style: const TextStyle(color: kTextPrimary, fontSize: 15),
                    decoration: const InputDecoration(
                      labelText: 'Search query',
                      hintText: 'e.g. gaming laptops under 80000',
                      prefixIcon: Icon(Icons.search_rounded, size: 18, color: kTextDim),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // Sites section
                  const Text(
                    'SITES',
                    style: TextStyle(
                      color: kTextDim, fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 1.2),
                  ),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final site in sites)
                        _SiteChip(
                          site: site,
                          onRemove: sites.length > 1 ? () => onRemoveSite(site) : null,
                        ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: addSiteController,
                          style: const TextStyle(color: kTextPrimary, fontSize: 14),
                          decoration: const InputDecoration(
                            hintText: 'Add site (e.g. myntra.com)',
                            isDense: true,
                            prefixIcon: Icon(Icons.add_link_rounded, size: 16, color: kTextDim),
                          ),
                          onSubmitted: onAddSite,
                        ),
                      ),
                      const SizedBox(width: 8),
                      _AddButton(onTap: () => onAddSite(addSiteController.text)),
                    ],
                  ),
                  const SizedBox(height: 20),

                  // Options
                  Container(
                    decoration: BoxDecoration(
                      color: kCard,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: kBorder),
                    ),
                    child: Column(
                      children: [
                        Padding(
                          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text('Effort per site', style: TextStyle(color: kTextSecondary, fontSize: 13)),
                              Text(
                                '$maxSteps',
                                style: const TextStyle(
                                  color: kPrimaryLit, fontSize: 13, fontWeight: FontWeight.w700,
                                  fontFamily: 'Courier New',
                                ),
                              ),
                            ],
                          ),
                        ),
                        Slider(
                          value: maxSteps.toDouble(), min: 5, max: 20, divisions: 15,
                          onChanged: (v) => onMaxStepsChanged(v.round()),
                        ),
                        const Divider(height: 1),
                        InkWell(
                          onTap: () => onSummarizeChanged(!summarize),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: const [
                                      Text('Compare & summarize', style: TextStyle(color: kTextPrimary, fontSize: 13, fontWeight: FontWeight.w500)),
                                      Text('AI picks the best deal across sites', style: TextStyle(color: kTextDim, fontSize: 11)),
                                    ],
                                  ),
                                ),
                                Switch(value: summarize, onChanged: onSummarizeChanged),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),

                  AppButton(
                    label: 'Compare ${sites.length} sites',
                    icon: Icons.compare_arrows_rounded,
                    onPressed: sites.isNotEmpty ? onRun : null,
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _SiteChip extends StatelessWidget {
  final String site;
  final VoidCallback? onRemove;

  const _SiteChip({required this.site, this.onRemove});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(10, 5, 6, 5),
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: kBorder),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6, height: 6,
            decoration: const BoxDecoration(shape: BoxShape.circle, color: kAccent),
          ),
          const SizedBox(width: 6),
          Text(site, style: const TextStyle(color: kTextPrimary, fontSize: 13)),
          if (onRemove != null) ...[
            const SizedBox(width: 4),
            GestureDetector(
              onTap: onRemove,
              child: const Icon(Icons.close_rounded, size: 14, color: kTextDim),
            ),
          ],
        ],
      ),
    );
  }
}

class _AddButton extends StatelessWidget {
  final VoidCallback onTap;
  const _AddButton({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          gradient: kGradientBlue,
          borderRadius: BorderRadius.circular(12),
          boxShadow: [BoxShadow(color: kPrimary.withOpacity(0.3), blurRadius: 12, offset: const Offset(0, 4))],
        ),
        child: const Icon(Icons.add_rounded, color: Colors.white, size: 20),
      ),
    );
  }
}

// ── Loading ───────────────────────────────────────────────────

class _LoadingView extends StatelessWidget {
  final int siteCount;
  const _LoadingView({super.key, required this.siteCount});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(40),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const CircularProgressIndicator(
                color: kPrimary,
                strokeWidth: 2,
              ),
              const SizedBox(height: 28),
              const Text(
                'Running parallel agents',
                style: TextStyle(
                  color: kTextPrimary, fontSize: 18, fontWeight: FontWeight.w700, letterSpacing: -0.3),
              ),
              const SizedBox(height: 6),
              Text(
                '$siteCount sites running simultaneously',
                style: const TextStyle(color: kTextDim, fontSize: 13),
              ),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.bolt_rounded, size: 13, color: kAccent),
                  const SizedBox(width: 4),
                  Text(
                    'Total time = slowest site, not sum',
                    style: TextStyle(color: kAccent.withOpacity(0.7), fontSize: 12),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── Results ───────────────────────────────────────────────────

class _ResultView extends StatefulWidget {
  final CompareResult result;
  final VoidCallback onReset;

  const _ResultView({super.key, required this.result, required this.onReset});

  @override
  State<_ResultView> createState() => _ResultViewState();
}

class _ResultViewState extends State<_ResultView> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    final tabCount = widget.result.sites.length + (widget.result.comparison != null ? 1 : 0);
    _tabController = TabController(length: tabCount, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final sites = widget.result.sites;
    final comparison = widget.result.comparison;

    return Column(
      children: [
        // Header
        SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Results',
                        style: TextStyle(
                          color: kTextPrimary, fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: -0.5),
                      ),
                      Text(
                        '"${widget.result.query}"',
                        style: const TextStyle(color: kTextDim, fontSize: 13),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                GestureDetector(
                  onTap: widget.onReset,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                    decoration: BoxDecoration(
                      color: kCard,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: kBorder),
                    ),
                    child: const Text('New search',
                        style: TextStyle(color: kTextSecondary, fontSize: 12, fontWeight: FontWeight.w500)),
                  ),
                ),
              ],
            ),
          ),
        ),

        // Tab bar
        Container(
          decoration: const BoxDecoration(
            border: Border(bottom: BorderSide(color: kBorder)),
          ),
          child: TabBar(
            controller: _tabController,
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            labelColor: kPrimaryLit,
            unselectedLabelColor: kTextDim,
            indicatorColor: kPrimary,
            indicatorWeight: 2,
            dividerColor: Colors.transparent,
            labelStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            unselectedLabelStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w400),
            tabs: [
              for (final site in sites)
                Tab(
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 6, height: 6,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: widget.result.results[site]?.success == true
                              ? kSuccess
                              : kError,
                        ),
                      ),
                      const SizedBox(width: 6),
                      Text(site),
                    ],
                  ),
                ),
              if (comparison != null)
                const Tab(
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.auto_awesome_rounded, size: 13, color: kPrimaryLit),
                      SizedBox(width: 5),
                      Text('AI Analysis'),
                    ],
                  ),
                ),
            ],
          ),
        ),

        // Tab content
        Expanded(
          child: TabBarView(
            controller: _tabController,
            children: [
              for (final site in sites)
                _SiteResultTab(site: site, result: widget.result.results[site]!),
              if (comparison != null)
                _AIAnalysisTab(comparison: comparison),
            ],
          ),
        ),
      ],
    );
  }
}

class _SiteResultTab extends StatelessWidget {
  final String site;
  final SiteResult result;

  const _SiteResultTab({required this.site, required this.result});

  @override
  Widget build(BuildContext context) {
    if (!result.success) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: kError.withOpacity(0.10),
                shape: BoxShape.circle,
                border: Border.all(color: kError.withOpacity(0.25)),
              ),
              child: const Icon(Icons.error_outline_rounded, color: kError, size: 28),
            ),
            const SizedBox(height: 14),
            Text(result.error ?? 'Failed to extract from $site',
                style: const TextStyle(color: kTextSecondary, fontSize: 13),
                textAlign: TextAlign.center),
          ],
        ),
      );
    }

    if (result.items.isEmpty) {
      return const Center(
        child: Text('No items found', style: TextStyle(color: kTextDim, fontSize: 14)),
      );
    }

    return ListView.builder(
      itemCount: result.items.length + 1,
      itemBuilder: (_, i) {
        if (i == 0) {
          return Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 8),
            child: Row(
              children: [
                Text(
                  '${result.total} items',
                  style: const TextStyle(color: kTextDim, fontSize: 11, letterSpacing: 0.5,
                      fontWeight: FontWeight.w600),
                ),
                const SizedBox(width: 10),
                Container(width: 1, height: 10, color: kBorder),
                const SizedBox(width: 10),
                Text(
                  '${result.stepsTaken} steps',
                  style: const TextStyle(color: kTextDim, fontSize: 11, letterSpacing: 0.5,
                      fontFamily: 'Courier New'),
                ),
              ],
            ),
          );
        }
        return ItemCard(item: result.items[i - 1], index: i - 1);
      },
    );
  }
}

class _AIAnalysisTab extends StatelessWidget {
  final Map<String, dynamic> comparison;
  const _AIAnalysisTab({required this.comparison});

  @override
  Widget build(BuildContext context) {
    final winnerKeys = ['price_winner', 'rating_winner', 'value_winner'];
    final winners = {for (final k in winnerKeys) if (comparison[k] != null) k: comparison[k].toString()};
    final otherKeys = comparison.keys.where((k) => !{...winnerKeys, 'recommendation'}.contains(k));

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Recommendation
        if (comparison['recommendation'] != null) ...[
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [kPrimaryDim.withOpacity(0.6), kAccentDim.withOpacity(0.4)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: kPrimary.withOpacity(0.25)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(
                  children: [
                    Icon(Icons.auto_awesome_rounded, size: 13, color: kPrimaryLit),
                    SizedBox(width: 6),
                    Text('AI Recommendation',
                        style: TextStyle(color: kPrimaryLit, fontSize: 11, fontWeight: FontWeight.w600,
                            letterSpacing: 0.5)),
                  ],
                ),
                const SizedBox(height: 10),
                Text(
                  comparison['recommendation'].toString(),
                  style: const TextStyle(color: kTextPrimary, fontSize: 14, height: 1.6),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
        ],

        // Winners grid
        if (winners.isNotEmpty) ...[
          const Text('WINNERS', style: TextStyle(color: kTextDim, fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 1.2)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final entry in winners.entries)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: kCard,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: kBorder),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        entry.key.replaceAll('_winner', '').toUpperCase(),
                        style: const TextStyle(color: kTextDim, fontSize: 10, letterSpacing: 0.8, fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        entry.value,
                        style: const TextStyle(color: kAccent, fontSize: 14, fontWeight: FontWeight.w700),
                      ),
                    ],
                  ),
                ),
            ],
          ),
          const SizedBox(height: 14),
        ],

        // Other fields
        for (final key in otherKeys)
          if (comparison[key] != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: kCard,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: kBorder),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      key.replaceAll('_', ' '),
                      style: const TextStyle(color: kTextDim, fontSize: 12, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        comparison[key].toString(),
                        style: const TextStyle(color: kTextSecondary, fontSize: 13),
                      ),
                    ),
                  ],
                ),
              ),
            ),
      ],
    );
  }
}

// ── Error ─────────────────────────────────────────────────────

class _ErrorView extends StatelessWidget {
  final String error;
  final VoidCallback onRetry;

  const _ErrorView({super.key, required this.error, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: kError.withOpacity(0.10),
                  shape: BoxShape.circle,
                  border: Border.all(color: kError.withOpacity(0.25)),
                ),
                child: const Icon(Icons.error_outline_rounded, size: 28, color: kError),
              ),
              const SizedBox(height: 18),
              Text(error,
                  style: const TextStyle(color: kTextSecondary, fontSize: 13),
                  textAlign: TextAlign.center),
              const SizedBox(height: 24),
              AppButton(label: 'Try Again', icon: Icons.refresh_rounded, onPressed: onRetry),
            ],
          ),
        ),
      ),
    );
  }
}
