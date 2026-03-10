// Helper to call the server
export async function callChatAPI(message: string, conversationId: string) {
  try {
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE ?? "";
    const url = baseUrl ? `${baseUrl}/chat` : "/chat";
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, message }),
    });
    if (!res.ok) throw new Error(`Chat API error: ${res.status}`);
    return res.json();
  } catch (err) {
    console.error("Error sending message:", err);
    return null;
  }
}
