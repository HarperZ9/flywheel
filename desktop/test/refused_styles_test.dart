// refused_styles_test.dart - the weights a family did not ship.
//
// mint_family returns refused weights in one of two places: inside the receipt
// when the family shipped, at the top level when it refused entirely. Reading
// only the first renders a family missing two weights as a complete one, and a
// card that cannot show that is not shipped.

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/widgets/variable_family_card.dart';

void main() {
  test('a shipped family names the weights it dropped', () {
    expect(
        refusedStyles(const {
          'refused': false,
          'instances': [
            {'style': 'Regular'}
          ],
          'receipt': {
            'family_id': 'abc',
            'refused_instances': [
              {'style': 'Black', 'weight': 900.0},
              {'style': 'Thin', 'weight': 100.0},
            ],
          },
        }),
        ['Black', 'Thin']);
  });

  test('a family that refused entirely still names them', () {
    // No receipt on this path, so a reader that only looks inside one reports
    // nothing refused for the case where everything was.
    expect(
        refusedStyles(const {
          'refused': true,
          'refusals': ['every instance was refused'],
          'refused_instances': [
            {'style': 'Regular'}
          ],
        }),
        ['Regular']);
  });

  test('a complete family refuses nothing', () {
    expect(
        refusedStyles(const {
          'refused': false,
          'receipt': {'family_id': 'abc', 'refused_instances': []},
        }),
        isEmpty);
  });

  test('a nameless refusal is still counted', () {
    // Dropping it would undercount, which is the direction that flatters.
    expect(
        refusedStyles(const {
          'receipt': {
            'refused_instances': [
              {'weight': 900.0}
            ]
          }
        }),
        ['?']);
  });

  test('wrongly typed or absent fields degrade to nothing refused', () {
    expect(refusedStyles(const {}), isEmpty);
    expect(refusedStyles(const {'receipt': 'abc'}), isEmpty);
    expect(refusedStyles(const {'refused_instances': 'Black'}), isEmpty);
    expect(refusedStyles(const {'receipt': {}, 'refused_instances': null}), isEmpty);
  });
}
