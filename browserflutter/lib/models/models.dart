class RunStatus {
  final String runId;
  final String status; // running | awaiting_approval | done | error
  final String? pendingAction;
  final Map<String, dynamic>? result;
  final String? error;

  const RunStatus({
    required this.runId,
    required this.status,
    this.pendingAction,
    this.result,
    this.error,
  });

  factory RunStatus.fromJson(Map<String, dynamic> j) => RunStatus(
        runId: j['run_id'] as String,
        status: j['status'] as String,
        pendingAction: j['pending_action'] as String?,
        result: j['result'] as Map<String, dynamic>?,
        error: j['error'] as String?,
      );

  bool get isRunning => status == 'running';
  bool get isAwaitingApproval => status == 'awaiting_approval';
  bool get isDone => status == 'done';
  bool get isError => status == 'error';
}

class AgentResult {
  final bool success;
  final Map<String, dynamic>? result;
  final String? summary;
  final int? stepsTaken;
  final String? error;
  final bool fromCache;

  const AgentResult({
    required this.success,
    this.result,
    this.summary,
    this.stepsTaken,
    this.error,
    this.fromCache = false,
  });

  List<Map<String, dynamic>> get items {
    final raw = result?['items'];
    if (raw == null) return [];
    return (raw as List).cast<Map<String, dynamic>>();
  }
}

class SiteResult {
  final bool success;
  final List<Map<String, dynamic>> items;
  final int total;
  final int stepsTaken;
  final String? error;

  const SiteResult({
    required this.success,
    required this.items,
    required this.total,
    required this.stepsTaken,
    this.error,
  });

  factory SiteResult.fromJson(Map<String, dynamic> j) => SiteResult(
        success: j['success'] as bool,
        items: (j['items'] as List? ?? []).cast<Map<String, dynamic>>(),
        total: j['total'] as int? ?? 0,
        stepsTaken: j['steps_taken'] as int? ?? 0,
        error: j['error'] as String?,
      );
}

class CompareResult {
  final bool success;
  final String query;
  final List<String> sites;
  final Map<String, SiteResult> results;
  final Map<String, dynamic>? comparison;

  const CompareResult({
    required this.success,
    required this.query,
    required this.sites,
    required this.results,
    this.comparison,
  });

  factory CompareResult.fromJson(Map<String, dynamic> j) {
    final rawResults = j['results'] as Map<String, dynamic>;
    return CompareResult(
      success: j['success'] as bool,
      query: j['query'] as String,
      sites: (j['sites'] as List).cast<String>(),
      results: rawResults.map((k, v) => MapEntry(k, SiteResult.fromJson(v as Map<String, dynamic>))),
      comparison: j['comparison'] as Map<String, dynamic>?,
    );
  }
}

class CachedResultEntry {
  final String goal;
  final int itemCount;
  final double ageHours;
  final String savedAt;

  const CachedResultEntry({
    required this.goal,
    required this.itemCount,
    required this.ageHours,
    required this.savedAt,
  });

  factory CachedResultEntry.fromJson(Map<String, dynamic> j) => CachedResultEntry(
        goal: j['goal'] as String,
        itemCount: j['item_count'] as int? ?? 0,
        ageHours: (j['age_hours'] as num?)?.toDouble() ?? 0.0,
        savedAt: j['saved_at'] as String? ?? '',
      );
}

class Preferences {
  final int maxSteps;
  final bool summarizeByDefault;
  final double cacheTtlHours;
  final String? preferredCurrency;
  final List<String> preferredSites;
  final String? defaultSession;

  const Preferences({
    this.maxSteps = 15,
    this.summarizeByDefault = false,
    this.cacheTtlHours = 1.0,
    this.preferredCurrency,
    this.preferredSites = const [],
    this.defaultSession,
  });

  factory Preferences.fromJson(Map<String, dynamic> j) => Preferences(
        maxSteps: j['max_steps'] as int? ?? 15,
        summarizeByDefault: j['summarize_by_default'] as bool? ?? false,
        cacheTtlHours: (j['cache_ttl_hours'] as num?)?.toDouble() ?? 1.0,
        preferredCurrency: j['preferred_currency'] as String?,
        preferredSites: (j['preferred_sites'] as List? ?? []).cast<String>(),
        defaultSession: j['default_session'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'max_steps': maxSteps,
        'summarize_by_default': summarizeByDefault,
        'cache_ttl_hours': cacheTtlHours,
        if (preferredCurrency != null) 'preferred_currency': preferredCurrency,
        if (preferredSites.isNotEmpty) 'preferred_sites': preferredSites,
        if (defaultSession != null) 'default_session': defaultSession,
      };
}
