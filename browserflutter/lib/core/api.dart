import 'dart:convert';
import 'package:http/http.dart' as http;

const String kBaseUrl = 'https://ai-browser-agent-cmyr.onrender.com';

class ApiException implements Exception {
  final int statusCode;
  final String message;
  const ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}

class ApiService {
  static final _client = http.Client();

  static Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) async {
    final res = await _client.post(
      Uri.parse('$kBaseUrl$path'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    final data = jsonDecode(res.body) as Map<String, dynamic>;
    if (res.statusCode >= 400) {
      throw ApiException(res.statusCode, data['detail']?.toString() ?? 'Unknown error');
    }
    return data;
  }

  static Future<Map<String, dynamic>> _get(String path) async {
    final res = await _client.get(Uri.parse('$kBaseUrl$path'));
    final data = jsonDecode(res.body) as Map<String, dynamic>;
    if (res.statusCode >= 400) {
      throw ApiException(res.statusCode, data['detail']?.toString() ?? 'Unknown error');
    }
    return data;
  }

  static Future<Map<String, dynamic>> _delete(String path) async {
    final res = await _client.delete(Uri.parse('$kBaseUrl$path'));
    final data = jsonDecode(res.body) as Map<String, dynamic>;
    if (res.statusCode >= 400) {
      throw ApiException(res.statusCode, data['detail']?.toString() ?? 'Unknown error');
    }
    return data;
  }

  // ── /run-async ──────────────────────────────────────────────

  static Future<Map<String, dynamic>> startRun({
    required String goal,
    int maxSteps = 15,
    bool summarize = false,
    String? session,
    bool useCache = false,
    double cacheTtlHours = 1.0,
  }) =>
      _post('/run-async', {
        'goal': goal,
        'max_steps': maxSteps,
        'summarize': summarize,
        if (session != null) 'session': session,
        'use_cache': useCache,
        'cache_ttl_hours': cacheTtlHours,
      });

  static Future<Map<String, dynamic>> pollRun(String runId) =>
      _get('/run-async/$runId');

  static Future<Map<String, dynamic>> approveAction(String runId) =>
      _post('/run-async/$runId/approve', {});

  static Future<Map<String, dynamic>> denyAction(String runId) =>
      _post('/run-async/$runId/deny', {});

  // ── /compare ────────────────────────────────────────────────

  static Future<Map<String, dynamic>> compare({
    required String query,
    required List<String> sites,
    int maxSteps = 12,
    bool summarize = true,
  }) =>
      _post('/compare', {
        'query': query,
        'sites': sites,
        'max_steps': maxSteps,
        'summarize': summarize,
      });

  // ── /memory/results ─────────────────────────────────────────

  static Future<Map<String, dynamic>> listResults() => _get('/memory/results');

  static Future<Map<String, dynamic>> deleteResult(String goal) =>
      _delete('/memory/results?goal=${Uri.encodeQueryComponent(goal)}');

  static Future<Map<String, dynamic>> clearAllResults() => _delete('/memory/results');

  // ── /memory/preferences ─────────────────────────────────────

  static Future<Map<String, dynamic>> getPreferences() => _get('/memory/preferences');

  static Future<Map<String, dynamic>> setPreferences(Map<String, dynamic> prefs) =>
      _post('/memory/preferences', prefs);

  static Future<Map<String, dynamic>> resetPreferences() => _delete('/memory/preferences');

  // ── /health ──────────────────────────────────────────────────

  static Future<Map<String, dynamic>> health() => _get('/health');
}
