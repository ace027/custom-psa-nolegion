import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import ErrorBoundary from "./ErrorBoundary";
import TimezoneSelect from "./TimezoneSelect";

function Harness({ initial, onPick }: { initial: string; onPick: (z: string) => void }) {
  const [z, setZ] = useState(initial);
  return <TimezoneSelect value={z} onChange={(v) => { setZ(v); onPick(v); }} />;
}

describe("TimezoneSelect", () => {
  it("filters, selects and returns the IANA name, with the offset shown", () => {
    const onPick = vi.fn();
    render(<Harness initial="America/Chicago" onPick={onPick} />);
    expect(screen.getByRole("option", { name: /^America\/Chicago \(UTC[+\u2212]\d\d:\d\d\)$/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter time zones"), { target: { value: "tokyo" } });
    expect(screen.queryByRole("option", { name: /Paris/ })).toBeNull();
    fireEvent.change(screen.getByLabelText("Time zone"), { target: { value: "Asia/Tokyo" } });
    expect(onPick).toHaveBeenCalledWith("Asia/Tokyo");
  });

  it("still shows a stored value that is not in the list", () => {
    render(<Harness initial="Mars/Olympus" onPick={() => {}} />);
    expect(screen.getByLabelText("Time zone")).toHaveValue("Mars/Olympus");
  });
});

describe("ErrorBoundary", () => {
  it("shows the fallback with the message and a Reload button", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const Boom = () => { throw new Error("kaboom"); };
    render(<ErrorBoundary><Boom /></ErrorBoundary>);
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("kaboom")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });
});
