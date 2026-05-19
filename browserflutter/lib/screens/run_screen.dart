import 'dart:async';
import 'package:flutter/material.dart';
import '../core/api.dart';
import '../core/theme.dart';
import '../models/models.dart';
import '../widgets/item_card.dart';
import '../widgets/app_button.dart';

class RunScreen extends StatefulWidget {
  const RunScreen({super.key});

  @override
  State<RunScreen> createState() => _RunScreenState();
}

class _RunScreenState extends State<RunScreen> {
  final _goalController = TextEditingController();
  final _sessionController = TextEditingController();

  int _maxSteps = 15;
  bool _summarize = false;
  bool _useCache = false;
  bool _showOptions = false;

  String? _runId;
  RunStatus? _status;
  AgentResult? _agentResult;
  String? _error;
  bool _loading = false;
  Timer? _pollTimer;

  @override
  void dispose() {
    _pollTimer?.cancel();
    _goalController.dispose();
    _sessionController.dispose();
    super.dispose();
  }

  Future<void> _startRun() async {
    final goal = _goalController.text.trim();
    if (goal.isEmpty) return;

    setState(() {
      _loading = true;
      _runId = null;
      _status = null;
      _agentResult = null;
      _error = null;
    });

    try {
      final res = await ApiService.startRun(
        goal: goal,
        maxSteps: _maxSteps,
        summarize: _summarize,
        session: _sessionController.text.trim().isEmpty ? null : _sessionController.text.trim(),
        useCache: _useCache,
      );
      final runId = res['run_id'] as String;
      setState(() => _runId = runId);
      _startPolling(runId);
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  void _startPolling(String runId) {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) => _poll(runId));
  }

  Future<void> _poll(String runId) async {
    try {
      final json = await ApiService.pollRun(runId);
      final status = RunStatus.fromJson(json);
      setState(() => _status = status);

      if (status.isAwaitingApproval) {
        _pollTimer?.cancel();
        _showApprovalDialog(runId, status.pendingAction ?? 'Unknown action');
      } else if (status.isDone) {
        _pollTimer?.cancel();
        final result = status.result ?? {};
        setState(() {
          _agentResult = AgentResult(
            success: result['success'] as bool? ?? false,
            result: result['result'] as Map<String, dynamic>?,
            summary: result['summary'] as String?,
            stepsTaken: result['steps_taken'] as int?,
            error: result['error'] as String?,
          );
          _loading = false;
        });
      } else if (status.isError) {
        _pollTimer?.cancel();
        setState(() {
          _error = status.error ?? 'Agent encountered an error';
          _loading = false;
        });
      }
    } catch (e) {
      _pollTimer?.cancel();
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  void _showApprovalDialog(String runId, String action) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        icon: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: kWarning.withOpacity(0.12),
            shape: BoxShape.circle,
            border: Border.all(color: kWarning.withOpacity(0.3)),
          ),
          child: const Icon(Icons.warning_amber_rounded, size: 28, color: kWarning),
        ),
        title: const Text('Approval required'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'The agent wants to perform this action:',
              style: TextStyle(color: kTextSecondary, fontSize: 13),
            ),
            const SizedBox(height: 10),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: kBg,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: kBorder),
              ),
              child: Text(
                action,
                style: const TextStyle(
                  fontFamily: 'Courier New',
                  fontSize: 13,
                  color: kAccent,
                  height: 1.5,
                ),
              ),
            ),
          ],
        ),
        actions: [
          OutlinedButton(
            onPressed: () async {
              Navigator.pop(ctx);
              await ApiService.denyAction(runId);
              _startPolling(runId);
            },
            style: OutlinedButton.styleFrom(
              foregroundColor: kTextSecondary,
              side: const BorderSide(color: kBorder),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            ),
            child: const Text('Deny'),
          ),
          Container(
            decoration: BoxDecoration(
              gradient: kGradientBlue,
              borderRadius: BorderRadius.circular(10),
              boxShadow: [BoxShadow(color: kPrimary.withOpacity(0.3), blurRadius: 12, offset: const Offset(0, 4))],
            ),
            child: TextButton(
              onPressed: () async {
                Navigator.pop(ctx);
                await ApiService.approveAction(runId);
                _startPolling(runId);
              },
              style: TextButton.styleFrom(
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
              ),
              child: const Text('Approve', style: TextStyle(fontWeight: FontWeight.w600)),
            ),
          ),
        ],
      ),
    );
  }

  void _reset() {
    _pollTimer?.cancel();
    setState(() {
      _runId = null;
      _status = null;
      _agentResult = null;
      _error = null;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBg,
      body: AnimatedSwitcher(
        duration: const Duration(milliseconds: 300),
        child: _agentResult != null
            ? _ResultView(key: const ValueKey('result'), result: _agentResult!, onNewRun: _reset)
            : _loading
                ? _LoadingView(key: const ValueKey('loading'), status: _status, runId: _runId)
                : _error != null
                    ? _ErrorView(key: const ValueKey('error'), error: _error!, onRetry: _reset)
                    : _InputView(
                        key: const ValueKey('input'),
                        goalController: _goalController,
                        sessionController: _sessionController,
                        maxSteps: _maxSteps,
                        summarize: _summarize,
                        useCache: _useCache,
                        showOptions: _showOptions,
                        onMaxStepsChanged: (v) => setState(() => _maxSteps = v),
                        onSummarizeChanged: (v) => setState(() => _summarize = v),
                        onUseCacheChanged: (v) => setState(() => _useCache = v),
                        onToggleOptions: () => setState(() => _showOptions = !_showOptions),
                        onRun: _startRun,
                      ),
      ),
    );
  }
}

// ── Input View ────────────────────────────────────────────────

class _InputView extends StatelessWidget {
  final TextEditingController goalController;
  final TextEditingController sessionController;
  final int maxSteps;
  final bool summarize;
  final bool useCache;
  final bool showOptions;
  final ValueChanged<int> onMaxStepsChanged;
  final ValueChanged<bool> onSummarizeChanged;
  final ValueChanged<bool> onUseCacheChanged;
  final VoidCallback onToggleOptions;
  final VoidCallback onRun;

  const _InputView({
    super.key,
    required this.goalController,
    required this.sessionController,
    required this.maxSteps,
    required this.summarize,
    required this.useCache,
    required this.showOptions,
    required this.onMaxStepsChanged,
    required this.onSummarizeChanged,
    required this.onUseCacheChanged,
    required this.onToggleOptions,
    required this.onRun,
  });

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        // Header
        SliverToBoxAdapter(
          child: _Header(),
        ),
        // Input card
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 0),
            child: _GoalInput(controller: goalController, onSubmit: onRun),
          ),
        ),
        // Cache quick-toggle (always visible)
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 10, 20, 0),
            child: GestureDetector(
              onTap: () => onUseCacheChanged(!useCache),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: useCache ? kPrimaryDim : kCard,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: useCache ? kPrimary.withOpacity(0.4) : kBorder,
                  ),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.bolt_rounded,
                      size: 15,
                      color: useCache ? kPrimaryLit : kTextDim,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Use cache',
                        style: TextStyle(
                          color: useCache ? kPrimaryLit : kTextSecondary,
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                    Text(
                      'saves to History',
                      style: TextStyle(
                        color: useCache ? kPrimary.withOpacity(0.6) : kTextDim,
                        fontSize: 11,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Switch(
                      value: useCache,
                      onChanged: onUseCacheChanged,
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        // Options toggle
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 10, 20, 0),
            child: GestureDetector(
              onTap: onToggleOptions,
              child: Row(
                children: [
                  const Icon(Icons.tune_rounded, size: 14, color: kTextDim),
                  const SizedBox(width: 6),
                  Text(
                    showOptions ? 'Hide options' : 'More options',
                    style: const TextStyle(
                      color: kTextDim, fontSize: 12, fontWeight: FontWeight.w500),
                  ),
                  const SizedBox(width: 4),
                  Icon(
                    showOptions ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                    size: 14,
                    color: kTextDim,
                  ),
                ],
              ),
            ),
          ),
        ),
        // Options panel
        if (showOptions)
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 10, 20, 0),
              child: _OptionsPanel(
                sessionController: sessionController,
                maxSteps: maxSteps,
                summarize: summarize,
                onMaxStepsChanged: onMaxStepsChanged,
                onSummarizeChanged: onSummarizeChanged,
              ),
            ),
          ),
        // Run button
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 40),
            child: AppButton(
              label: 'Run Agent',
              icon: Icons.terminal_rounded,
              onPressed: onRun,
            ),
          ),
        ),
      ],
    );
  }
}

class _Header extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(20, MediaQuery.of(context).padding.top + 20, 20, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  gradient: kGradientBlue,
                  borderRadius: BorderRadius.circular(12),
                  boxShadow: [BoxShadow(color: kPrimary.withOpacity(0.35), blurRadius: 16, offset: const Offset(0, 6))],
                ),
                child: const Icon(Icons.language_rounded, color: Colors.white, size: 20),
              ),
              const SizedBox(width: 12),
              const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'BrowseFlow',
                    style: TextStyle(
                      color: kTextPrimary, fontSize: 18, fontWeight: FontWeight.w800, letterSpacing: -0.3,
                    ),
                  ),
                  Text(
                    'AI Browser Agent',
                    style: TextStyle(color: kTextDim, fontSize: 12, letterSpacing: 0.3),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 28),
          const Text(
            'What should the\nagent do?',
            style: TextStyle(
              color: kTextPrimary, fontSize: 28, fontWeight: FontWeight.w800,
              letterSpacing: -0.8, height: 1.15,
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            'Describe a task in plain English — the agent handles the rest.',
            style: TextStyle(color: kTextSecondary, fontSize: 14, height: 1.5),
          ),
        ],
      ),
    );
  }
}

class _GoalInput extends StatelessWidget {
  final TextEditingController controller;
  final VoidCallback onSubmit;

  const _GoalInput({required this.controller, required this.onSubmit});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: kCard,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: kBorder),
      ),
      child: TextField(
        controller: controller,
        maxLines: 4,
        minLines: 3,
        style: const TextStyle(color: kTextPrimary, fontSize: 15, height: 1.55),
        decoration: const InputDecoration(
          hintText:
              'e.g. Search Amazon for gaming laptops under ₹80,000 and show me the top 5',
          hintStyle: TextStyle(color: kTextDim, fontSize: 14, height: 1.5),
          border: InputBorder.none,
          enabledBorder: InputBorder.none,
          focusedBorder: InputBorder.none,
          contentPadding: EdgeInsets.all(16),
          fillColor: Colors.transparent,
          filled: false,
        ),
        textInputAction: TextInputAction.done,
        onSubmitted: (_) => onSubmit(),
      ),
    );
  }
}

class _OptionsPanel extends StatelessWidget {
  final TextEditingController sessionController;
  final int maxSteps;
  final bool summarize;
  final ValueChanged<int> onMaxStepsChanged;
  final ValueChanged<bool> onSummarizeChanged;

  const _OptionsPanel({
    required this.sessionController,
    required this.maxSteps,
    required this.summarize,
    required this.onMaxStepsChanged,
    required this.onSummarizeChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: kCard,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: kBorder),
      ),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 6),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('How hard to try', style: TextStyle(color: kTextSecondary, fontSize: 13)),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: kPrimaryDim,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    '$maxSteps',
                    style: const TextStyle(
                      color: kPrimaryLit, fontSize: 13, fontWeight: FontWeight.w700,
                      fontFamily: 'Courier New',
                    ),
                  ),
                ),
              ],
            ),
          ),
          Slider(
            value: maxSteps.toDouble(),
            min: 5,
            max: 30,
            divisions: 25,
            onChanged: (v) => onMaxStepsChanged(v.round()),
          ),
          const Divider(height: 1),
          _OptionTile(
            label: 'Summarize results',
            subtitle: 'AI will explain what it found',
            value: summarize,
            onChanged: onSummarizeChanged,
          ),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
            child: TextField(
              controller: sessionController,
              style: const TextStyle(color: kTextPrimary, fontSize: 14),
              decoration: const InputDecoration(
                labelText: 'Stay logged in on',
                hintText: 'e.g. amazon.in',
                prefixIcon: Icon(Icons.lock_open_outlined, size: 16, color: kTextDim),
                isDense: true,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _OptionTile extends StatelessWidget {
  final String label;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  const _OptionTile({
    required this.label,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => onChanged(!value),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
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

// ── Loading View ──────────────────────────────────────────────

class _LoadingView extends StatelessWidget {
  final RunStatus? status;
  final String? runId;

  const _LoadingView({super.key, this.status, this.runId});

  String get _label => switch (status?.status) {
        'running'            => 'Agent working',
        'awaiting_approval'  => 'Awaiting approval',
        _                    => 'Starting agent',
      };

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(40),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _PulsingOrb(),
              const SizedBox(height: 40),
              Text(
                _label,
                style: const TextStyle(
                  color: kTextPrimary, fontSize: 20, fontWeight: FontWeight.w700, letterSpacing: -0.3,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Agent is browsing the web...',
                style: TextStyle(color: kTextDim, fontSize: 13),
              ),
              if (runId != null) ...[
                const SizedBox(height: 24),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: kSurface,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: kBorder),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text('run/', style: TextStyle(color: kTextDim, fontSize: 12, fontFamily: 'Courier New')),
                      Text(
                        runId!,
                        style: const TextStyle(
                          color: kAccent, fontSize: 12, fontFamily: 'Courier New', fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _PulsingOrb extends StatefulWidget {
  @override
  State<_PulsingOrb> createState() => _PulsingOrbState();
}

class _PulsingOrbState extends State<_PulsingOrb> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _scale;
  late Animation<double> _glow;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400))
      ..repeat(reverse: true);
    _scale = Tween(begin: 0.85, end: 1.0).animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
    _glow = Tween(begin: 0.2, end: 0.6).animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (context0, child0) => Transform.scale(
        scale: _scale.value,
        child: Container(
          width: 88,
          height: 88,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: kGradientBlue,
            boxShadow: [
              BoxShadow(
                color: kPrimary.withOpacity(_glow.value),
                blurRadius: 40,
                spreadRadius: 8,
              ),
              BoxShadow(
                color: kAccent.withOpacity(_glow.value * 0.5),
                blurRadius: 60,
                spreadRadius: 16,
              ),
            ],
          ),
          child: const Icon(Icons.language_rounded, color: Colors.white, size: 36),
        ),
      ),
    );
  }
}

// ── Result View ───────────────────────────────────────────────

class _ResultView extends StatelessWidget {
  final AgentResult result;
  final VoidCallback onNewRun;

  const _ResultView({super.key, required this.result, required this.onNewRun});

  @override
  Widget build(BuildContext context) {
    final items = result.items;

    return CustomScrollView(
      slivers: [
        // Header
        SliverToBoxAdapter(
          child: SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Container(
                              width: 8, height: 8,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: result.success ? kSuccess : kError,
                                boxShadow: [BoxShadow(
                                  color: (result.success ? kSuccess : kError).withOpacity(0.5),
                                  blurRadius: 8,
                                )],
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(
                              result.success ? 'Run complete' : 'Run failed',
                              style: const TextStyle(
                                color: kTextSecondary, fontSize: 12, letterSpacing: 0.3),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${items.length} items extracted',
                          style: const TextStyle(
                            color: kTextPrimary, fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: -0.5),
                        ),
                      ],
                    ),
                  ),
                  GestureDetector(
                    onTap: onNewRun,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                      decoration: BoxDecoration(
                        color: kCard,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: kBorder),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.add_rounded, size: 14, color: kTextSecondary),
                          SizedBox(width: 5),
                          Text('New run', style: TextStyle(color: kTextSecondary, fontSize: 13, fontWeight: FontWeight.w500)),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),

        // Stats row
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
            child: Row(
              children: [
                _StatChip(label: '${result.stepsTaken ?? 0}', sublabel: 'steps'),
                const SizedBox(width: 8),
                if (result.fromCache) _StatChip(label: 'CACHED', sublabel: 'result', accent: kAccent),
                if (result.summarize == true) ...[
                  const SizedBox(width: 8),
                  _StatChip(label: 'AI', sublabel: 'summary', accent: kPrimary),
                ],
              ],
            ),
          ),
        ),

        // Summary card
        if (result.summary != null)
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 14, 20, 0),
              child: Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [kPrimaryDim.withOpacity(0.6), kAccentDim.withOpacity(0.4)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: kPrimary.withOpacity(0.25)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.auto_awesome_rounded, size: 14, color: kPrimaryLit),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        result.summary!,
                        style: const TextStyle(color: kTextPrimary, fontSize: 13, height: 1.55),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),

        // Items header
        if (items.isNotEmpty)
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 6),
              child: Row(
                children: [
                  const Text(
                    'RESULTS',
                    style: TextStyle(
                      color: kTextDim, fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 1.2,
                    ),
                  ),
                ],
              ),
            ),
          ),

        // Items list
        if (items.isNotEmpty)
          SliverList(
            delegate: SliverChildBuilderDelegate(
              (_, i) => ItemCard(item: items[i], index: i),
              childCount: items.length,
            ),
          )
        else
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.all(40),
              child: Center(
                child: Text(
                  result.error ?? 'No items extracted',
                  style: const TextStyle(color: kError, fontSize: 14),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
          ),

        const SliverToBoxAdapter(child: SizedBox(height: 80)),
      ],
    );
  }
}

extension on AgentResult {
  bool get summarize => summary != null;
}

class _StatChip extends StatelessWidget {
  final String label;
  final String sublabel;
  final Color? accent;

  const _StatChip({required this.label, required this.sublabel, this.accent});

  @override
  Widget build(BuildContext context) {
    final color = accent ?? kTextDim;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: kCard,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: accent != null ? color.withOpacity(0.3) : kBorder),
      ),
      child: Column(
        children: [
          Text(
            label,
            style: TextStyle(
              color: accent != null ? color : kTextSecondary,
              fontSize: 13,
              fontWeight: FontWeight.w700,
              fontFamily: 'Courier New',
            ),
          ),
          Text(
            sublabel,
            style: const TextStyle(color: kTextDim, fontSize: 10, letterSpacing: 0.3),
          ),
        ],
      ),
    );
  }
}

// ── Error View ────────────────────────────────────────────────

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
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  color: kError.withOpacity(0.10),
                  shape: BoxShape.circle,
                  border: Border.all(color: kError.withOpacity(0.25)),
                ),
                child: const Icon(Icons.error_outline_rounded, size: 32, color: kError),
              ),
              const SizedBox(height: 20),
              const Text(
                'Something went wrong',
                style: TextStyle(color: kTextPrimary, fontSize: 18, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 8),
              Text(
                error,
                style: const TextStyle(color: kTextSecondary, fontSize: 13, height: 1.5),
                textAlign: TextAlign.center,
                maxLines: 4,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 28),
              AppButton(label: 'Try Again', icon: Icons.refresh_rounded, onPressed: onRetry),
            ],
          ),
        ),
      ),
    );
  }
}

