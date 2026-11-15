// Per-platform adapter pack. Each is a selector CONFIG over the generic behavior — no graded
// logic anywhere. Selectors are sensible templates; verify/adjust against the live page before a
// real run (LMS DOMs change). `locateAssessment` tells the workflow author which steps to tag
// `assess` so the engine halts there.
import { registerAdapter } from "./types.mjs";
import { makeGenericAdapter } from "./generic.mjs";

const PLATFORMS = {
  coursera: {
    nextSelector: 'button[data-testid="next-item"], .rc-NextButton button',
    assessmentSelector: '[data-testid="quiz"], .rc-QuizComponent',
    assessmentLabel: "Coursera graded quiz/assignment",
    captureKind: "dom",
  },
  udemy: {
    nextSelector: '[data-purpose="go-to-next"], button[aria-label="Next"]',
    assessmentSelector: '[data-purpose="quiz-container"], .quiz--container--',
    assessmentLabel: "Udemy quiz/practice test",
    captureKind: "dom",
  },
  "linkedin-learning": {
    nextSelector: 'button.classroom-toc-item__link--next, button[aria-label*="Next"]',
    assessmentSelector: '.chapter-quiz, [data-testid="quiz"]',
    assessmentLabel: "LinkedIn Learning chapter quiz",
    captureKind: "dom",
  },
  edx: {
    nextSelector: '.sequence-nav-button.button-next, button.next',
    assessmentSelector: '.problems-wrapper, .xblock-student_view .problem',
    assessmentLabel: "edX graded problem/exam",
    captureKind: "dom",
  },
  credly: {
    // Badge wallet: organize/export earned badges (no coursework/assessment surface).
    assessmentSelector: null,
    assessmentLabel: "none (badge wallet)",
    captureKind: "dom",
  },
  "microsoft-learn": {
    // learn.microsoft.com/training — free self-paced modules; "knowledge checks" flagged as assess.
    // (Certification EXAMS like AZ-900 are proctored/paid and are NOT driven by this engine at all.)
    nextSelector: 'button[data-bi-name="next"], .next-section a, a[data-bi-name="unit-next"]',
    assessmentSelector: '.knowledge-check, [data-bi-name="knowledge-check"]',
    assessmentLabel: "Microsoft Learn knowledge check",
    captureKind: "dom",
  },
  nonprofitready: {
    // nonprofitready.org — free self-paced courses + certificates; end-of-course quizzes flagged.
    nextSelector: 'button.continue, a.next, .lesson-next',
    assessmentSelector: '.quiz, .assessment, .test',
    assessmentLabel: "NonprofitReady course quiz",
    captureKind: "dom",
  },
  selfpaced: {
    // Generic self-paced fallback (Stanford free / UMich non-hosted / misc): mark-complete + next.
    nextSelector: 'button.next, a.next, [aria-label*="Next" i]',
    assessmentSelector: '.quiz, .assessment, .exam',
    assessmentLabel: "graded step (verify selector per course)",
    captureKind: "dom",
  },
};

for (const [name, config] of Object.entries(PLATFORMS)) {
  registerAdapter(name, makeGenericAdapter({ ...config, certId: `cert:${name}` }));
}

export const LMS_PLATFORMS = Object.keys(PLATFORMS);
