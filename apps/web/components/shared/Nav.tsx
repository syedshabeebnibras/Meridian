import Link from "next/link";
import { Github } from "lucide-react";

import { auth } from "@/auth";
import { Button } from "@/components/ui/Button";
import { Logo } from "./Logo";

export async function Nav() {
  const session = await auth();
  const signedIn = !!session?.user?.id;

  return (
    <header className="sticky top-0 z-40 border-b border-[var(--color-border)]/60 bg-[var(--color-bg)]/60 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-5">
        <Link href="/" className="transition-opacity hover:opacity-80">
          <Logo />
        </Link>
        <nav className="flex items-center gap-1">
          <Button asChild variant="ghost" size="sm">
            <a
              href="https://github.com/syedshabeebnibras/Meridian"
              target="_blank"
              rel="noreferrer"
              aria-label="GitHub repository"
            >
              <Github className="size-4" />
            </a>
          </Button>
          {signedIn ? (
            <Button asChild variant="primary" size="sm" className="ml-2">
              <Link href="/chat">Open chat</Link>
            </Button>
          ) : (
            <>
              <Button asChild variant="ghost" size="sm">
                <Link href="/sign-in">Sign in</Link>
              </Button>
              <Button asChild variant="primary" size="sm" className="ml-2">
                <Link href="/sign-up">Get started</Link>
              </Button>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
