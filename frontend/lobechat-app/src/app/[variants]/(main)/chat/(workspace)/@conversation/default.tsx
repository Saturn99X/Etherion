/**
 * @conversation — Etherion chat conversation panel.
 *
 * Replaces LobeChat's original ChatList + ChatInput with Etherion's
 * ThreadView, which owns:
 *   - Message rendering (via useThreadStore)
 *   - Goal submission + SSE streaming (via GoalInputBar → sendGoalAndStream)
 *   - Plan/Act + Search toggles
 *   - Team selector
 *   - Job status tracking + execution trace
 */

import { ThreadView } from '@/etherion/ui/chat/thread-view';
import { DynamicLayoutProps } from '@/types/next';
import { RouteVariants } from '@/utils/server/routeVariants';
import ChatHydration from './features/ChatHydration';

const ChatConversation = async (props: DynamicLayoutProps) => {
  // ChatHydration bootstraps the LobeChat session/message store from URL params.
  // Keep it so LobeChat's session routing (activeId, activeTopicId) stays consistent
  // even though we render Etherion's ThreadView as the primary chat surface.
  await RouteVariants.getIsMobile(props); // consume route variant (no-op side-effect)

  return (
    <>
      {/* Bootstrap LobeChat session context (needed for session store / URL routing) */}
      <ChatHydration />
      {/* Etherion conversation surface — full height, self-contained */}
      <ThreadView />
    </>
  );
};

ChatConversation.displayName = 'ChatConversation';

export default ChatConversation;
