# Example: Bulletin public feedback check

User prompt:

```text
Read this public feedback thread and assess whether the Bulletin site should emphasize a visible agent pipeline instead of a primary Q&A form.
```

Expected behavior:

1. Treat the supplied public thread URL as a source pointer, not as permission to post.
2. Capture the relevant public comments and their URLs.
3. Label each feedback claim `reported` until directly read.
4. Define a falsifier, such as finding stronger current feedback that asks for Q&A-first positioning.
5. Distinguish product intent from implementation readiness.
6. Produce a public-safe summary with comment URLs, excluded private material, and next website-copy changes.

Expected result shape:

```text
Reported: users want to see agents coordinate through Bulletin.
Checked: exact public comment URLs and text snippets read during this task.
Unknown: whether the current website implements that positioning.
Next action: update public copy or demo only from approved public artifacts.
```
