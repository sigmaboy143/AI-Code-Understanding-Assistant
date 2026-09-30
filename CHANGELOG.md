# Change Log

All notable changes to the "aicode-understanding-assistant" extension will be documented in this file.

Check [Keep a Changelog](http://keepachangelog.com/) for recommendations on how to structure this file.

## [Unreleased]

- Initial release
- Added an extension-host test suite: activation and manifest-contribution
  checks, activity-bar view checks, configuration checks, webview panel asset
  and CSP checks, and command-to-webview message-flow coverage in both mock and
  real mode (real mode runs against a local HTTP server returning a genuine
  `AnalysisResult`). No production code changed.