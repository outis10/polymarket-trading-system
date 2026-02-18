import { create } from "zustand";

interface AccountState {
    bankrollReal: number | null;
    setBankrollReal: (value: number | null) => void;
}

export const useAccountStore = create<AccountState>((set) => ({
    bankrollReal: null,
    setBankrollReal: (value) => set({ bankrollReal: value }),
}));
