// motion.dart -- the single duration decision point. When the operating
// system asks for reduced motion, every audited animation duration is
// zero and the final state renders immediately.
import 'package:flutter/material.dart';

const Duration _normalTransition = Duration(milliseconds: 150);

Duration motionDuration(BuildContext context,
        {Duration normal = _normalTransition}) =>
    MediaQuery.disableAnimationsOf(context) ? Duration.zero : normal;
