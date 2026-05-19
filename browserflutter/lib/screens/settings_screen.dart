import 'package:flutter/material.dart';
import '../core/api.dart';
import '../core/theme.dart';
import '../models/models.dart';
import '../widgets/app_button.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _currencyController = TextEditingController();
  final _sessionController = TextEditingController();
  final _addSiteController = TextEditingController();

  bool _loading = true;
  bool _saving = false;
  String? _error;

  int _maxSteps = 15;
  bool _summarize = false;
  double _cacheTtl = 1.0;
  List<String> _preferredSites = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _currencyController.dispose();
    _sessionController.dispose();
    _addSiteController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final json = await ApiService.getPreferences();
      final prefs = Preferences.fromJson(json);
      setState(() {
        _maxSteps = prefs.maxSteps;
        _summarize = prefs.summarizeByDefault;
        _cacheTtl = prefs.cacheTtlHours;
        _preferredSites = List.from(prefs.preferredSites);
        _currencyController.text = prefs.preferredCurrency ?? '';
        _sessionController.text = prefs.defaultSession ?? '';
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final updates = <String, dynamic>{
        'max_steps': _maxSteps,
        'summarize_by_default': _summarize,
        'cache_ttl_hours': _cacheTtl,
        if (_currencyController.text.trim().isNotEmpty)
          'preferred_currency': _currencyController.text.trim(),
        if (_preferredSites.isNotEmpty) 'preferred_sites': _preferredSites,
        if (_sessionController.text.trim().isNotEmpty)
          'default_session': _sessionController.text.trim(),
      };
      await ApiService.setPreferences(updates);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Preferences saved')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed: $e')),
        );
      }
    } finally {
      setState(() => _saving = false);
    }
  }

  Future<void> _resetPrefs() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Reset preferences?'),
        content: const Text(
          'All preferences will be reset to their default values.',
          style: TextStyle(color: kTextSecondary, fontSize: 14),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel', style: TextStyle(color: kTextSecondary)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Reset', style: TextStyle(color: kPrimary, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
    if (confirm == true) {
      await ApiService.resetPreferences();
      await _load();
    }
  }

  void _addSite(String site) {
    site = site.trim().toLowerCase();
    if (site.isNotEmpty && !_preferredSites.contains(site)) {
      setState(() => _preferredSites.add(site));
    }
    _addSiteController.clear();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBg,
      body: CustomScrollView(
        slivers: [
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
                            'Settings',
                            style: TextStyle(
                              color: kTextPrimary, fontSize: 28, fontWeight: FontWeight.w800,
                              letterSpacing: -0.8),
                          ),
                          SizedBox(height: 2),
                          Text(
                            'Customise how the agent behaves',
                            style: TextStyle(color: kTextSecondary, fontSize: 13),
                          ),
                        ],
                      ),
                    ),
                    GestureDetector(
                      onTap: _loading ? null : _resetPrefs,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                        decoration: BoxDecoration(
                          color: kCard,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: kBorder),
                        ),
                        child: const Text(
                          'Reset',
                          style: TextStyle(color: kTextSecondary, fontSize: 12, fontWeight: FontWeight.w500),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
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
          else
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 40),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _SectionLabel('HOW THE AGENT WORKS'),
                    const SizedBox(height: 10),
                    _SettingsCard(children: [
                      _SliderRow(
                        label: 'How hard to try',
                        value: _maxSteps.toDouble(),
                        displayValue: '$_maxSteps',
                        min: 5, max: 30, divisions: 25,
                        onChanged: (v) => setState(() => _maxSteps = v.round()),
                      ),
                      const _CardDivider(),
                      _SliderRow(
                        label: 'Remember results for',
                        value: _cacheTtl,
                        displayValue: '${_cacheTtl.toStringAsFixed(1)}h',
                        min: 0.5, max: 24.0, divisions: 47,
                        onChanged: (v) => setState(() => _cacheTtl = (v * 2).round() / 2),
                      ),
                      const _CardDivider(),
                      _ToggleRow(
                        label: 'Always summarize results',
                        subtitle: 'AI explains what it found after every run',
                        value: _summarize,
                        onChanged: (v) => setState(() => _summarize = v),
                      ),
                    ]),
                    const SizedBox(height: 20),
                    _SectionLabel('YOUR DEFAULTS'),
                    const SizedBox(height: 10),
                    _SettingsCard(children: [
                      _TextFieldRow(
                        controller: _currencyController,
                        label: 'Show prices in',
                        hint: 'INR',
                        icon: Icons.currency_rupee_rounded,
                      ),
                      const _CardDivider(),
                      _TextFieldRow(
                        controller: _sessionController,
                        label: 'Stay logged in on',
                        hint: 'amazon.in',
                        icon: Icons.lock_open_outlined,
                      ),
                    ]),
                    const SizedBox(height: 20),
                    _SectionLabel('MY FAVOURITE SITES'),
                    const SizedBox(height: 10),
                    _SettingsCard(children: [
                      if (_preferredSites.isNotEmpty) ...[
                        Padding(
                          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                          child: Wrap(
                            spacing: 8,
                            runSpacing: 6,
                            children: [
                              for (final site in _preferredSites)
                                Container(
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
                                        width: 5, height: 5,
                                        decoration: const BoxDecoration(
                                          shape: BoxShape.circle, color: kAccent),
                                      ),
                                      const SizedBox(width: 6),
                                      Text(site, style: const TextStyle(color: kTextPrimary, fontSize: 12)),
                                      const SizedBox(width: 4),
                                      GestureDetector(
                                        onTap: () => setState(() => _preferredSites.remove(site)),
                                        child: const Icon(Icons.close_rounded, size: 13, color: kTextDim),
                                      ),
                                    ],
                                  ),
                                ),
                            ],
                          ),
                        ),
                        const _CardDivider(),
                      ],
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
                        child: Row(
                          children: [
                            Expanded(
                              child: TextField(
                                controller: _addSiteController,
                                style: const TextStyle(color: kTextPrimary, fontSize: 14),
                                decoration: const InputDecoration(
                                  hintText: 'Add site (e.g. myntra.com)',
                                  isDense: true,
                                  border: InputBorder.none,
                                  enabledBorder: InputBorder.none,
                                  focusedBorder: InputBorder.none,
                                  contentPadding: EdgeInsets.zero,
                                  filled: false,
                                ),
                                onSubmitted: _addSite,
                              ),
                            ),
                            GestureDetector(
                              onTap: () => _addSite(_addSiteController.text),
                              child: Container(
                                padding: const EdgeInsets.all(6),
                                decoration: BoxDecoration(
                                  color: kPrimaryDim,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: const Icon(Icons.add_rounded, size: 16, color: kPrimaryLit),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ]),
                    const SizedBox(height: 28),
                    AppButton(
                      label: 'Save preferences',
                      icon: Icons.check_rounded,
                      onPressed: _save,
                      loading: _saving,
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

// ── Shared sub-widgets ────────────────────────────────────────

class _SectionLabel extends StatelessWidget {
  final String label;
  const _SectionLabel(this.label);

  @override
  Widget build(BuildContext context) => Text(
        label,
        style: const TextStyle(
          color: kTextDim, fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 1.2),
      );
}

class _SettingsCard extends StatelessWidget {
  final List<Widget> children;
  const _SettingsCard({required this.children});

  @override
  Widget build(BuildContext context) => Container(
        decoration: BoxDecoration(
          color: kCard,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: kBorder),
        ),
        child: Column(children: children),
      );
}

class _CardDivider extends StatelessWidget {
  const _CardDivider();

  @override
  Widget build(BuildContext context) => Container(height: 1, color: kBorder);
}

class _SliderRow extends StatelessWidget {
  final String label;
  final double value;
  final String displayValue;
  final double min;
  final double max;
  final int divisions;
  final ValueChanged<double> onChanged;

  const _SliderRow({
    required this.label,
    required this.value,
    required this.displayValue,
    required this.min,
    required this.max,
    required this.divisions,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label, style: const TextStyle(color: kTextSecondary, fontSize: 13)),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: kPrimaryDim, borderRadius: BorderRadius.circular(6)),
                child: Text(
                  displayValue,
                  style: const TextStyle(
                    color: kPrimaryLit, fontSize: 12, fontWeight: FontWeight.w700,
                    fontFamily: 'Courier New',
                  ),
                ),
              ),
            ],
          ),
          Slider(value: value, min: min, max: max, divisions: divisions, onChanged: onChanged),
        ],
      ),
    );
  }
}

class _ToggleRow extends StatelessWidget {
  final String label;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  const _ToggleRow({
    required this.label, required this.subtitle,
    required this.value, required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => onChanged(!value),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, style: const TextStyle(color: kTextPrimary, fontSize: 13, fontWeight: FontWeight.w500)),
                  Text(subtitle, style: const TextStyle(color: kTextDim, fontSize: 11)),
                ],
              ),
            ),
            Switch(value: value, onChanged: onChanged),
          ],
        ),
      ),
    );
  }
}

class _TextFieldRow extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hint;
  final IconData icon;

  const _TextFieldRow({
    required this.controller, required this.label,
    required this.hint, required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(
        children: [
          Icon(icon, size: 16, color: kTextDim),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(color: kTextSecondary, fontSize: 11, letterSpacing: 0.3)),
                const SizedBox(height: 2),
                TextField(
                  controller: controller,
                  style: const TextStyle(color: kTextPrimary, fontSize: 14),
                  decoration: InputDecoration(
                    hintText: hint,
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    contentPadding: EdgeInsets.zero,
                    isDense: true,
                    filled: false,
                    hintStyle: const TextStyle(color: kTextDim, fontSize: 14),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
