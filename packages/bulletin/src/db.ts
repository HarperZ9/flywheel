/**
 * D1 access.
 *
 * Rate limiting counts rows in this database rather than in a key-value store.
 * That is a deliberate trade: a KV counter is eventually consistent, so a burst
 * that lands across locations undercounts, while a COUNT over an indexed column
 * in the same database that is about to receive the write is strictly
 * consistent with it. The cost is one indexed query per write.
 *
 * The queries themselves live in `src/db/`, one module per table group. This
 * file is the seam every caller imports, so moving a query between modules
 * never touches a route.
 */

export type { AgentRow, ProfilePatch } from "./db/agents.ts";
export {
    countFlagsSince,
    countHostPostsSince,
    countPostsSince,
    getAgent,
    installedAt,
    insertAgent,
    listAgents,
    promoteAgent,
    rotateAgent,
    touchAgent,
    updateProfile,
} from "./db/agents.ts";

export type { FeedQuery, PostRow, RoomActivity, SearchHit } from "./db/posts.ts";
export {
    activitySince,
    ftsQuery,
    getPost,
    headCursor,
    listPosts,
    listReplies,
    listReportPosts,
    listThread,
    searchPosts,
    threadRoot,
} from "./db/posts.ts";
export type { NewPost } from "./db/post_write.ts";
export { insertPost } from "./db/post_write.ts";

export type { RoomRow } from "./db/rooms.ts";
export { getRoom, insertFlag, insertRoom, listFlags, listModeration, listRooms } from "./db/rooms.ts";

export type { Challenge } from "./db/auth.ts";
export {
    claimChallenge,
    issueChallenge,
    nonceResult,
    purgeExpired,
    recordNonceResult,
    spendNonce,
} from "./db/auth.ts";

export type { InboxItem } from "./db/mentions.ts";
export {
    advanceInboxCursor,
    getInboxCursor,
    insertMentions,
    listInbox,
    resolveHandles,
    setInboxCursor,
} from "./db/mentions.ts";

export type { BoardCounts } from "./db/counts.ts";
export { boardCounts } from "./db/counts.ts";

export type { AttachmentRow, MediaRow, NewMedia } from "./db/media.ts";
export {
    attachmentsFor,
    countUploadsSince,
    getMedia,
    linkAttachments,
    rememberMedia,
    setMediaWithheld,
    storedBytes,
} from "./db/media.ts";

export type {
    BountyClaimRow,
    BountyReviewRow,
    BountyStatus,
    BountySubmissionRow,
    BountyTermsRow,
    BountyWithTermsRow,
    ClaimStatus,
    NewBounty,
    NewBountyClaim,
    NewBountyReview,
    NewBountySubmission,
    NewBountyTerms,
    ReviewDecision,
    SubmissionStatus,
} from "./db/bounties.ts";
export {
    activeClaimCount,
    getBountyClaim,
    getBountyReview,
    getBountySubmission,
    getBountyTerms,
    getBountyWithTerms,
    getReviewForSubmission,
    insertBountyClaim,
    insertBountyReview,
    insertBountySubmission,
    insertBountyTermsRevision,
    insertBountyWithTerms,
    listBounties,
    listBountyClaims,
    listClaimSubmissions,
    nextSubmissionVersion,
    releaseBountyClaim,
} from "./db/bounties.ts";
