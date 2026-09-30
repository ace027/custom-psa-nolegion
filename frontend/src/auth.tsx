import { useQuery } from "@tanstack/react-query";
import { ApiError, Me, api } from "./api";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    retry: false,
    queryFn: async (): Promise<Me | null> => {
      try {
        return await api<Me>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
  });
}

export const can = (me: Me | null | undefined, permission: string) =>
  !!me && me.permissions.includes(permission);
