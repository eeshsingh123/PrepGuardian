import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MessageSquare, Clock, User, Bot } from 'lucide-react';
import { useAuth } from '../lib/auth';
import { fetchConversations, fetchConversation } from '../lib/api';
import type { ConversationSummary, ConversationFull } from '../lib/api';

interface TranscriptsProps {
  isDarkMode: boolean;
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function Transcripts({ isDarkMode }: TranscriptsProps) {
  const { user } = useAuth();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const dark = isDarkMode;

  const conversationsQuery = useQuery({
    queryKey: ['conversations', user?.user_id],
    queryFn: () => fetchConversations(user!.user_id),
    enabled: !!user,
  });

  const transcriptQuery = useQuery({
    queryKey: ['transcript', selectedSessionId],
    queryFn: () => fetchConversation(selectedSessionId!),
    enabled: !!selectedSessionId,
  });

  return (
    <div className="flex h-[calc(100vh-73px)]">
      {/* Left Panel: Conversation List */}
      <div className={`w-80 flex-shrink-0 border-r flex flex-col ${dark ? 'border-gray-800 bg-[#0a0a0a]' : 'border-gray-200 bg-gray-50'}`}>
        <div className={`px-4 py-3 border-b ${dark ? 'border-gray-800' : 'border-gray-200'}`}>
          <h2 className={`text-sm font-medium uppercase tracking-wider ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
            Past Conversations
          </h2>
        </div>

        <div className="flex-1 overflow-y-auto">
          {conversationsQuery.isLoading && (
            <div className={`p-4 text-sm ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
              Loading conversations…
            </div>
          )}

          {conversationsQuery.isError && (
            <div className="p-4 text-sm text-red-400">
              Failed to load conversations
            </div>
          )}

          {conversationsQuery.data?.length === 0 && (
            <div className={`p-4 text-sm ${dark ? 'text-gray-600' : 'text-gray-400'}`}>
              No conversations yet. Start a voice session to create one.
            </div>
          )}

          {conversationsQuery.data?.map((conv: ConversationSummary) => (
            <button
              key={conv.session_id}
              onClick={() => setSelectedSessionId(conv.session_id)}
              className={`w-full text-left px-4 py-3 border-b transition-colors ${
                selectedSessionId === conv.session_id
                  ? (dark ? 'bg-gray-800/50 border-gray-700' : 'bg-blue-50 border-gray-200')
                  : (dark ? 'border-gray-800/50 hover:bg-gray-800/30' : 'border-gray-100 hover:bg-gray-100')
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className={`text-xs ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
                  {formatDate(conv.started_at)}
                </span>
                <span className={`text-xs flex items-center gap-1 ${dark ? 'text-gray-600' : 'text-gray-400'}`}>
                  <Clock className="w-3 h-3" />
                  {formatDuration(conv.duration_seconds)}
                </span>
              </div>
              <p className={`text-sm line-clamp-2 ${dark ? 'text-gray-300' : 'text-gray-700'}`}>
                {conv.preview || 'No transcript available'}
              </p>
              <div className={`flex items-center gap-2 mt-1.5 text-xs ${dark ? 'text-gray-600' : 'text-gray-400'}`}>
                <MessageSquare className="w-3 h-3" />
                <span>{conv.turn_count} turns</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Right Panel: Transcript Viewer */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!selectedSessionId ? (
          <div className="flex-1 flex items-center justify-center">
            <div className={`text-center ${dark ? 'text-gray-600' : 'text-gray-400'}`}>
              <MessageSquare className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p className="text-sm">Select a conversation to view the transcript</p>
            </div>
          </div>
        ) : transcriptQuery.isLoading ? (
          <div className={`flex-1 flex items-center justify-center text-sm ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
            Loading transcript…
          </div>
        ) : transcriptQuery.isError ? (
          <div className="flex-1 flex items-center justify-center text-sm text-red-400">
            Failed to load transcript
          </div>
        ) : transcriptQuery.data ? (
          <TranscriptView conversation={transcriptQuery.data} isDarkMode={dark} />
        ) : null}
      </div>
    </div>
  );
}


function TranscriptView({ conversation, isDarkMode }: { conversation: ConversationFull; isDarkMode: boolean }) {
  const dark = isDarkMode;

  return (
    <>
      {/* Transcript Header */}
      <div className={`px-6 py-3 border-b flex items-center justify-between ${dark ? 'border-gray-800' : 'border-gray-200'}`}>
        <div>
          <p className={`text-xs uppercase tracking-wider ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
            Session Transcript
          </p>
          <p className={`text-xs mt-0.5 ${dark ? 'text-gray-600' : 'text-gray-400'}`}>
            {formatDate(conversation.started_at)}
          </p>
        </div>
        <div className={`flex items-center gap-4 text-xs ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatDuration(conversation.duration_seconds)}
          </span>
          <span>{conversation.turn_count} turns</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
        {conversation.turns.map((turn, index) => (
          <div
            key={index}
            className={`flex gap-3 ${turn.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {turn.role === 'agent' && (
              <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${dark ? 'bg-purple-500/20 text-purple-400' : 'bg-purple-100 text-purple-600'}`}>
                <Bot className="w-3.5 h-3.5" />
              </div>
            )}
            <div
              className={`max-w-[70%] px-3.5 py-2.5 rounded-xl text-sm leading-relaxed ${
                turn.role === 'user'
                  ? (dark
                      ? 'bg-blue-600/20 text-blue-100 rounded-br-sm'
                      : 'bg-blue-50 text-blue-900 border border-blue-100 rounded-br-sm')
                  : (dark
                      ? 'bg-gray-800 text-gray-200 rounded-bl-sm'
                      : 'bg-white text-gray-800 border border-gray-200 rounded-bl-sm')
              }`}
            >
              <p className="whitespace-pre-wrap">{turn.text}</p>
              <span className={`block text-[10px] mt-1 ${
                turn.role === 'user'
                  ? (dark ? 'text-blue-400/50' : 'text-blue-400')
                  : (dark ? 'text-gray-600' : 'text-gray-400')
              }`}>
                {formatTime(turn.timestamp)}
              </span>
            </div>
            {turn.role === 'user' && (
              <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${dark ? 'bg-blue-500/20 text-blue-400' : 'bg-blue-100 text-blue-600'}`}>
                <User className="w-3.5 h-3.5" />
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
