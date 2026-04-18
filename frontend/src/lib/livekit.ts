import { api } from "./api";

export interface VoiceTokenResponse {
  room: string;
  token: string;
  ws_url: string;
  conversation_id: string;
}

export async function fetchVoiceToken(
  device: string,
  conversationId?: string,
): Promise<VoiceTokenResponse> {
  return api<VoiceTokenResponse>("/voice/token", {
    method: "POST",
    body: JSON.stringify({
      device_id: device,
      conversation_id: conversationId,
    }),
  });
}
