# Release checklist

Run the full test suite before you tag a release. The suite takes about four
minutes on a laptop, and most of that time goes to the timing tests.

Write the changelog entry while the change is fresh. Name what changed for the
reader, then name what they need to do, if anything. Keep each entry short.

Tag the merge commit on main and publish a GitHub release for the tag. The
publish workflow starts when the release is published.

After the workflow finishes, install the new version in a clean virtual
environment and run the version command. If the version is wrong, stop and
find out why before you announce anything.
