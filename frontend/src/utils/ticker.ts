import type { EventData } from "../types/events";

export function inferTicker(eventId: string, event: EventData): string {
    const chainlink = (event.chainlink_symbol || "").trim().toUpperCase();
    if (chainlink) return chainlink;

    const haystack = [
        eventId,
        event.icon,
        event.name,
        event.description,
    ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

    if (haystack.includes("btc") || haystack.includes("bitcoin")) return "BTC";
    if (haystack.includes("eth") || haystack.includes("ethereum")) return "ETH";
    if (haystack.includes("sol") || haystack.includes("solana")) return "SOL";
    if (haystack.includes("xrp") || haystack.includes("ripple")) return "XRP";
    return "OTHER";
}
