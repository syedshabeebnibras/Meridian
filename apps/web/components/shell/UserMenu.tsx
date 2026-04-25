"use client";

import { signOut } from "next-auth/react";
import { LogOut } from "lucide-react";

import { Button } from "@/components/ui/Button";

interface Props {
  name: string;
  email: string;
}

export function UserMenu({ name, email }: Props) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-[var(--color-fg)]">
          {name || email || "User"}
        </div>
        <div className="truncate text-[10px] text-[var(--color-fg-subtle)]">{email}</div>
      </div>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Sign out"
        onClick={() => {
          void signOut({ callbackUrl: "/" });
        }}
      >
        <LogOut className="size-4" aria-hidden />
      </Button>
    </div>
  );
}
