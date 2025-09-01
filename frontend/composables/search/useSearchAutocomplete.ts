/**
 * Composable for providing search field autocomplete suggestions
 * Integrates with the query language parser to provide context-aware suggestions
 */

interface SuggestionItem {
    value: string;
    type: "field" | "operator" | "value";
    description?: string;
}

interface AutocompleteState {
    suggestions: SuggestionItem[];
    isVisible: boolean;
    selectedIndex: number;
    triggerPosition: number;
}

export const useSearchAutocomplete = () => {
    const { getSortingFields } = useApiClient();

    // State
    const state = reactive<AutocompleteState>({
        suggestions: [],
        isVisible: false,
        selectedIndex: -1,
        triggerPosition: 0,
    });

    // Cache for field names
    const fieldNames = ref<string[]>([]);
    const fieldsLoaded = ref(false);

    // Operators that can be suggested
    const operators = [
        { value: "=", description: "equals" },
        { value: "!=", description: "not equals" },
        { value: ">", description: "greater than" },
        { value: "<", description: "less than" },
        { value: ">=", description: "greater than or equal" },
        { value: "<=", description: "less than or equal" },
        { value: ":", description: "contains (substring)" },
        { value: "=~", description: "regex match" },
        { value: "!~", description: "regex not match" },
        { value: "#", description: "fuzzy match (0.7 similarity)" },
        { value: ":*", description: "field exists" },
    ];

    // Boolean operators
    const _booleanOperators = [
        { value: "AND", description: "logical AND" },
        { value: "OR", description: "logical OR" },
        { value: "NOT", description: "logical NOT" },
    ];

    /**
     * Load available field names from the API
     */
    const loadFieldNames = async (forceRefresh: boolean = false) => {
        if (fieldsLoaded.value && !forceRefresh) return;

        try {
            const response = await getSortingFields();
            if (response.fields && response.fields.length > 0) {
                // Process the fields to strip metadata. prefix and _name suffix for display
                const processedFields: string[] = [];

                response.fields.forEach((originalField: string) => {
                    let displayField = originalField;

                    if (originalField.startsWith("metadata.")) {
                        // Strip the metadata. prefix for display
                        displayField = originalField.substring("metadata.".length);
                    }

                    // Strip _name suffix for cleaner display
                    if (displayField.endsWith("_name")) {
                        displayField = displayField.substring(0, displayField.length - "_name".length);
                    }

                    processedFields.push(displayField);
                });

                fieldNames.value = processedFields
                    .filter((field, index, array) => array.indexOf(field) === index)
                    .sort();

                fieldsLoaded.value = true;
            }
        } catch (error) {
            console.warn("Failed to load field names for autocomplete:", error);
            fieldsLoaded.value = false; // Reset on error to allow retry
        }
    };

    /**
     * Filter field names based on partial input
     */
    const filterFields = (partial: string): SuggestionItem[] => {
        if (!partial)
            return fieldNames.value.map((field) => ({
                value: field,
                type: "field" as const,
                description: getFieldDescription(field),
            }));

        const filtered = fieldNames.value.filter((field) => field.toLowerCase().includes(partial.toLowerCase()));

        // Sort by relevance (exact match, starts with, contains)
        filtered.sort((a, b) => {
            const aLower = a.toLowerCase();
            const bLower = b.toLowerCase();
            const partialLower = partial.toLowerCase();

            if (aLower === partialLower) return -1;
            if (bLower === partialLower) return 1;
            if (aLower.startsWith(partialLower)) return -1;
            if (bLower.startsWith(partialLower)) return 1;
            return 0;
        });

        return filtered.map((field) => ({
            value: field,
            type: "field" as const,
            description: getFieldDescription(field),
        }));
    };

    /**
     * Get a description for a field name
     */
    const getFieldDescription = (field: string): string => {
        if (field.endsWith("_name")) {
            return "Related entity name";
        }
        if (field.endsWith("_id")) {
            return "Entity ID";
        }
        if (field.includes("date") || field.includes("time")) {
            return "Date/time field";
        }
        // Check if this is a known database column vs metadata field
        const knownDatabaseFields = ["id", "name", "created_at", "last_edited_at"];
        if (knownDatabaseFields.includes(field)) {
            return "Database field";
        }
        // If not a known database field, it's likely a metadata field
        return "Metadata field";
    };

    /**
     * Analyze the query context to determine what type of suggestion to show
     */
    const analyzeContext = (beforeCursor: string): "field" | "operator" | "value" => {
        const trimmed = beforeCursor.trim();

        // If empty, suggest field names
        if (!trimmed) {
            return "field";
        }

        // If after opening parenthesis, suggest field names
        if (/\(\s*$/.test(trimmed)) {
            return "field";
        }

        // Split by AND/OR/NOT to get segments, but preserve the operators
        const segments = trimmed.split(/\b(AND|OR|NOT)\b/i);

        // Get the last segment (what we're currently working on)
        const currentSegment = segments[segments.length - 1].trim();

        // If the current segment is empty and the previous token was a boolean operator,
        // suggest field names
        if (!currentSegment && segments.length >= 2) {
            const prevToken = segments[segments.length - 2];
            if (/^(AND|OR|NOT)$/i.test(prevToken.trim())) {
                return "field";
            }
        }

        // If currentSegment is empty, suggest fields
        if (!currentSegment) {
            return "field";
        }

        // Check if we're in a value context: field operator "value" or field operator value
        const valuePattern = /([\w.-]+)\s*([><=!:~#*]+)\s*(.+)$/i;
        const valueMatch = valuePattern.exec(currentSegment);
        if (valueMatch && valueMatch[3]) {
            return "value";
        }

        // Check if we have field + operator but no value yet: "field ="
        const fieldOperatorPattern = /([\w.-]+)\s*([><=!:~#*]+)(\s*)$/i;
        const fieldOpMatch = fieldOperatorPattern.exec(currentSegment);
        if (fieldOpMatch) {
            const operatorPart = fieldOpMatch[2];
            const hasTrailingSpace = fieldOpMatch[3].length > 0;

            // If there's a space after the operator, always go to value context
            if (hasTrailingSpace) {
                return "value";
            }

            // No trailing space - check if this is a complete operator
            const isCompleteOperator = operators.some((op) => op.value === operatorPart);
            const hasLongerOperators = operators.some(
                (op) => op.value.startsWith(operatorPart) && op.value !== operatorPart,
            );

            if (isCompleteOperator && !hasLongerOperators) {
                return "value";
            }
            // If there are longer operators possible, stay in operator context for suggestions
        }

        // Check if we're typing a partial operator after a field name
        const partialOperatorPattern = /([\w.-]+)\s*([><=!:~#*]*)$/i;
        const partialOpMatch = partialOperatorPattern.exec(currentSegment);
        if (partialOpMatch) {
            const fieldName = partialOpMatch[1];
            const partialOp = partialOpMatch[2];

            // Check if this is a valid field name
            const isValidField = fieldNames.value.some((f) => f.toLowerCase() === fieldName.toLowerCase());

            if (isValidField) {
                // If there's any operator character started, or field followed by space, suggest operators
                if (partialOp || currentSegment.includes(" ")) {
                    return "operator";
                }
            }
        }

        // Check if we have just a field name (possibly with trailing space)
        const fieldPattern = /^([\w.-]+)(\s*)$/i;
        const fieldMatch = fieldPattern.exec(currentSegment);

        if (fieldMatch) {
            const fieldName = fieldMatch[1];

            // Check if this is a valid field name
            const isValidField = fieldNames.value.some((f) => f.toLowerCase() === fieldName.toLowerCase());

            if (isValidField) {
                // If we have a valid field name, suggest operators
                return "operator";
            } else {
                // If not a valid field name, suggest field completions
                return "field";
            }
        }

        // Default to field suggestions
        return "field";
    };

    /**
     * Filter operators based on partial input
     */
    const filterOperators = (partial: string): SuggestionItem[] => {
        if (!partial) {
            // If no partial input, return all operators
            return operators.map((op) => ({
                value: op.value,
                type: "operator" as const,
                description: op.description,
            }));
        }

        // Filter operators that start with the partial input
        const filtered = operators.filter((op) => op.value.startsWith(partial));

        // Sort by length (shorter operators first for exact matches)
        filtered.sort((a, b) => {
            if (a.value.length !== b.value.length) {
                return a.value.length - b.value.length;
            }
            return a.value.localeCompare(b.value);
        });

        return filtered.map((op) => ({
            value: op.value,
            type: "operator" as const,
            description: op.description,
        }));
    };

    /**
     * Extract partial operator from the query
     */
    const extractPartialOperator = (beforeCursor: string): string => {
        // Look for field followed by partial operator characters (including multi-char operators)
        const match = beforeCursor.match(/([\w.-]+)\s*([><=!:~#*]*)$/i);
        if (match) {
            return match[2] || "";
        }
        return "";
    };

    /**
     * Get suggestions based on current query and cursor position
     */
    const getSuggestions = async (query: string, cursorPosition: number): Promise<SuggestionItem[]> => {
        if (!fieldsLoaded.value) {
            await loadFieldNames();
        }

        const beforeCursor = query.slice(0, cursorPosition);
        const context = analyzeContext(beforeCursor);
        const suggestions: SuggestionItem[] = [];

        if (context === "field") {
            // Extract partial field name (including hyphens)
            const fieldMatch = beforeCursor.match(/(?:^|\s|\(|AND\s+|OR\s+|NOT\s+)([\w.-]*)$/i);
            const partial = fieldMatch ? fieldMatch[1] : "";

            // Get field suggestions
            const fieldSuggestions = filterFields(partial);
            suggestions.push(...fieldSuggestions);
        } else if (context === "operator") {
            // Extract partial operator and filter suggestions
            const partialOperator = extractPartialOperator(beforeCursor);
            const operatorSuggestions = filterOperators(partialOperator);
            suggestions.push(...operatorSuggestions);
        } else if (context === "value") {
            // When in value context, don't show any suggestions
            // User should be able to type freely without autocomplete interference
            return [];
        }

        return suggestions.slice(0, 20); // Limit to 20 suggestions
    };

    /**
     * Show suggestions for the given query and cursor position
     */
    const showSuggestions = async (query: string, cursorPosition: number) => {
        const suggestions = await getSuggestions(query, cursorPosition);

        state.suggestions = suggestions;
        state.isVisible = suggestions.length > 0;
        state.selectedIndex = suggestions.length > 0 ? 0 : -1;
        state.triggerPosition = cursorPosition;
    };

    /**
     * Hide suggestions
     */
    const hideSuggestions = () => {
        state.isVisible = false;
        state.suggestions = [];
        state.selectedIndex = -1;
    };

    /**
     * Navigate through suggestions
     */
    const navigateSuggestions = (direction: "up" | "down") => {
        if (!state.isVisible || state.suggestions.length === 0) return;

        if (direction === "up") {
            state.selectedIndex = state.selectedIndex <= 0 ? state.suggestions.length - 1 : state.selectedIndex - 1;
        } else {
            state.selectedIndex = state.selectedIndex >= state.suggestions.length - 1 ? 0 : state.selectedIndex + 1;
        }
    };

    /**
     * Get the currently selected suggestion
     */
    const getSelectedSuggestion = (): SuggestionItem | null => {
        if (state.selectedIndex >= 0 && state.selectedIndex < state.suggestions.length) {
            return state.suggestions[state.selectedIndex];
        }
        return null;
    };

    /**
     * Apply a suggestion to the query
     */
    const applySuggestion = (
        query: string,
        cursorPosition: number,
        suggestion: SuggestionItem,
    ): { newQuery: string; newCursorPosition: number } => {
        const beforeCursor = query.slice(0, cursorPosition);
        const afterCursor = query.slice(cursorPosition);

        let newQuery: string;
        let newCursorPosition: number;

        if (suggestion.type === "field") {
            // Use the stripped field name directly - the backend should handle it
            const fieldName = suggestion.value;

            // Replace the partial field name being typed (including hyphens)
            const fieldMatch = beforeCursor.match(/(?:^|\s|\(|AND\s+|OR\s+|NOT\s+)([\w.-]*)$/i);
            if (fieldMatch) {
                // We found a partial field pattern, replace it
                const partialField = fieldMatch[1];
                const replaceStart = cursorPosition - partialField.length;
                newQuery = query.slice(0, replaceStart) + fieldName + afterCursor;
                newCursorPosition = replaceStart + fieldName.length;
            } else {
                // No partial field found, just append
                newQuery = beforeCursor + fieldName + afterCursor;
                newCursorPosition = cursorPosition + fieldName.length;
            }
        } else if (suggestion.type === "operator") {
            // Handle operator replacement - need to replace any partial operator already typed
            const operatorMatch = beforeCursor.match(/([\w.-]+)\s*([><=!:~#*]*)$/i);
            if (operatorMatch) {
                // We found a field followed by a partial operator, replace the partial operator
                const partialOperator = operatorMatch[2];
                const replaceStart = cursorPosition - partialOperator.length;

                // Check if we need space after the operator
                const needsSpaceAfter = ![":", ":*"].includes(suggestion.value);
                const suffix = needsSpaceAfter ? " " : "";

                newQuery = query.slice(0, replaceStart) + suggestion.value + suffix + afterCursor;
                newCursorPosition = replaceStart + suggestion.value.length + suffix.length;
            } else {
                // No partial operator found, add operator with appropriate spacing
                const needsSpaceBefore = beforeCursor.trim() !== "" && !beforeCursor.endsWith(" ");
                const needsSpaceAfter = ![":", ":*"].includes(suggestion.value);

                const prefix = needsSpaceBefore ? " " : "";
                const suffix = needsSpaceAfter ? " " : "";

                newQuery = beforeCursor + prefix + suggestion.value + suffix + afterCursor;
                newCursorPosition = cursorPosition + prefix.length + suggestion.value.length + suffix.length;
            }
        } else {
            // Default case for other types
            newQuery = beforeCursor + suggestion.value + afterCursor;
            newCursorPosition = cursorPosition + suggestion.value.length;
        }

        return { newQuery, newCursorPosition };
    };

    /**
     * Clear the cached field names and force a reload on next request
     */
    const clearFieldCache = () => {
        fieldsLoaded.value = false;
        fieldNames.value = [];
    };

    /**
     * Refresh field names from the API
     */
    const refreshFieldNames = async () => {
        await loadFieldNames(true);
    };

    /**
     * Set the selected index directly
     */
    const setSelectedIndex = (index: number) => {
        state.selectedIndex = index;
    };

    return {
        state: readonly(state),
        showSuggestions,
        hideSuggestions,
        navigateSuggestions,
        getSelectedSuggestion,
        applySuggestion,
        loadFieldNames,
        clearFieldCache,
        refreshFieldNames,
        setSelectedIndex,
    };
};
