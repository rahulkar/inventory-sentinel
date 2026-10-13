import { ArrowUp, Check, ChevronRight, Copy, Maximize2, MessageCircle, Mic, Plus, Settings, Sparkles, Square, Trash2, X } from "lucide-react";

/** The chat UI's icons, from the app's icon pack (Lucide), at the sizes the chat layout expects. */
export const IconChat = ({ size = 24 }: { size?: number }) => <MessageCircle size={size} aria-hidden="true" />;
export const IconClose = ({ size = 18 }: { size?: number }) => <X size={size} aria-hidden="true" />;
export const IconExpand = () => <Maximize2 size={16} aria-hidden="true" />;
export const IconPlus = () => <Plus size={16} aria-hidden="true" />;
export const IconMic = () => <Mic size={18} aria-hidden="true" />;
export const IconStop = () => <Square size={14} fill="currentColor" aria-hidden="true" />;
export const IconSend = () => <ArrowUp size={18} aria-hidden="true" />;
export const IconCopy = () => <Copy size={14} aria-hidden="true" />;
export const IconCheck = () => <Check size={14} aria-hidden="true" />;
export const IconTrash = () => <Trash2 size={15} aria-hidden="true" />;
export const IconGear = () => <Settings size={16} aria-hidden="true" />;
export const IconSparkle = () => <Sparkles size={14} aria-hidden="true" />;
export const IconChevron = () => <ChevronRight size={14} aria-hidden="true" />;
