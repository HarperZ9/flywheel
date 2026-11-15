Could you rename this to `parse_header`, since it only parses the header?

This loop allocates a new buffer on every pass, which makes large files slow.
Moving the allocation above the loop would fix it.

Nice catch on the off-by-one in the pager.
