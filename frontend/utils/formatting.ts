/**
 * Pure utility functions for data formatting and UI helpers
 * These are stateless functions that don't depend on Vue reactivity
 */

import { APP_CONFIG } from "~/config/app.config";

/**
 * Format field names for display in sorting dropdown
 */
export function formatFieldLabel(field: string): string {
    if (field.startsWith("metadata.")) {
        const metadataKey = field.replace("metadata.", "");
        return metadataKey.replace(/-/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
    }
    return field
        .replace(/_/g, " ")
        .replace(/\b\w/g, (l) => l.toUpperCase())
        .replace(" Name", "");
}

/**
 * Generate filename for entity downloads with timestamp
 */
export const createEntityDownloadFilename = (entityCount: number): string => {
    const now = new Date();
    const timestamp = now
        .toISOString()
        .slice(0, 19)
        .replace(/[-T:]/g, (match) => (match === "T" ? "_" : "-"));

    const multipleEntities = entityCount > 1 ? "entities" : "entity";
    return `${APP_CONFIG.downloads.fileNamePrefix}-${entityCount}-${multipleEntities}-${timestamp}.json`;
};

/**
 * Download data as JSON file to user's computer
 */
export const downloadAsJsonFile = (data: unknown, filename: string): void => {
    const jsonContent = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonContent], { type: "application/json" });
    const downloadUrl = URL.createObjectURL(blob);

    const downloadLink = document.createElement("a");
    downloadLink.href = downloadUrl;
    downloadLink.download = filename;
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
    URL.revokeObjectURL(downloadUrl);
};

/**
 * Check if a field name represents a status field
 */
export const isStatusField = (key: string): boolean => {
    const normalizedKey = key.toLowerCase();
    return (
        normalizedKey.includes("status") ||
        normalizedKey.includes("state") ||
        normalizedKey.includes("phase") ||
        normalizedKey === "health" ||
        normalizedKey === "condition" ||
        normalizedKey === "progress"
    );
};

/**
 * Get status badge color based on value using custom design system colors
 */
export const getStatusBadgeColor = (
    value: unknown,
): "status-completed" | "status-in-progress" | "status-active" | "status-failed" | "status-neutral" => {
    const stringValue = String(value).toLowerCase();

    // Success states - completed/done operations
    if (stringValue.includes("done") || stringValue.includes("stopped") || stringValue.includes("completed")) {
        return "status-completed";
    }

    // Warning states - ongoing processes
    if (
        stringValue.includes("warning") ||
        stringValue.includes("pending") ||
        stringValue.includes("moved-to-tape") ||
        stringValue.includes("processing") ||
        stringValue.includes("progress") ||
        stringValue.includes("partial")
    ) {
        return "status-in-progress";
    }

    // Error states - failed operations
    if (
        stringValue.includes("error") ||
        stringValue.includes("fail") ||
        stringValue.includes("invalid") ||
        stringValue.includes("disabled") ||
        stringValue.includes("rejected") ||
        stringValue === "false"
    ) {
        return "status-failed";
    }

    // Neutral states - not-registered and other neutral states
    if (
        stringValue.includes("not-registered") ||
        stringValue.includes("unknown") ||
        stringValue.includes("undefined") ||
        stringValue.includes("null")
    ) {
        return "status-neutral";
    }

    // Info states - active/running operations
    if (
        stringValue.includes("info") ||
        stringValue.includes("active") ||
        stringValue.includes("draft") ||
        stringValue.includes("scheduled") ||
        stringValue.includes("queued")
    ) {
        return "status-active";
    }

    // Default neutral for unknown/unmatched states
    return "status-neutral";
};

/**
 * Format field names for metadata display
 */
export const formatFieldName = (key: string): string => {
    return key
        .split("_")
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(" ");
};

/**
 * Copy text to clipboard with fallback for older browsers
 */
export async function copyToClipboard(text: string): Promise<void> {
    try {
        await navigator.clipboard.writeText(text);
    } catch {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        textArea.style.position = "fixed";
        textArea.style.opacity = "0";
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand("copy");
        document.body.removeChild(textArea);
    }
}

/**
 * Format timestamp for display
 */
export const formatTimestamp = (timestamp: string): string => {
    try {
        const date = new Date(timestamp);
        return date.toLocaleString("en-UK", {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
            timeZoneName: "short",
        });
    } catch {
        return timestamp;
    }
};

/**
 * Format bytes to GiB for file sizes
 */
export const formatSizeInGiB = (bytes: unknown): string => {
    const bytesNumber = Number(bytes);
    if (isNaN(bytesNumber) || bytesNumber < 0) return "N/A";
    const gigabytes = bytesNumber / (1024 * 1024 * 1024);
    return `${gigabytes.toFixed(2)} GiB`;
};
