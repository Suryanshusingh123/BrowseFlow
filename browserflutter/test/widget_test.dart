import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:browserflutter/main.dart';

void main() {
  testWidgets('App launches and shows bottom nav', (tester) async {
    await tester.pumpWidget(const BrowserAgentApp());
    expect(find.byType(NavigationBar), findsOneWidget);
  });
}
