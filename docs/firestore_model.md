# Firestore data model

## Collections
- `accounts/{accountId}`
  - Fields: `name`, `ownerId`, `createdAt`.
  - Subcollections:
    - `members/{uid}`: `{ userId, displayName, email?, photoUrl?, role: "admin"|"staff", assignedConversationIds: string[], createdAt }`
    - `conversations/{conversationId}`: `{ accountId, customerName, assignedResponderId?, lastMessageAt, aiEnabled }`
      - `messages/{messageId}`: `{ authorType: "customer"|"agent"|"ai", authorId?, text, sentAt, direction: "inbound"|"outbound", status, attachments? }`

## Access patterns
- Look up a user membership via collection group query on `members` filtered by `userId`.
- Agents work inside a single account; role controls admin/staff abilities.
- Conversations and messages stay inside the owning account; media is kept out of Firestore.
