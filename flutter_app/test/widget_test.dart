import 'package:flutter_test/flutter_test.dart';

import 'package:powwash_workspace/app.dart';

void main() {
  testWidgets('PowWash app renders workspace shell', (tester) async {
    await tester.pumpWidget(const PowWashApp());
    expect(find.text('Pow Team Chat'), findsOneWidget);
  });
}
