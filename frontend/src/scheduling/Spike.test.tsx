import { render, screen } from "@testing-library/react";
import { format, getDay, parse, startOfWeek } from "date-fns";
import { enUS } from "date-fns/locale/en-US";
import { Calendar, dateFnsLocalizer } from "react-big-calendar";
import withDragAndDrop from "react-big-calendar/lib/addons/dragAndDrop";

const localizer = dateFnsLocalizer({ format, parse, startOfWeek, getDay, locales: { "en-US": enUS } });
const DnDCalendar = withDragAndDrop(Calendar);

const resources = [
  { id: 1, title: "Sam Tech" },
  { id: 2, title: "Alex Tech" },
];
const events = [
  { id: 1, title: "#101 Acme", start: new Date(2030, 0, 7, 9), end: new Date(2030, 0, 7, 10), resourceId: 1 },
  { id: 2, title: "#102 Globex", start: new Date(2030, 0, 7, 11), end: new Date(2030, 0, 7, 12), resourceId: 2 },
];

describe("react-big-calendar drag and drop under React 19", () => {
  it("renders resources and events without React errors", () => {
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const { container } = render(
      <div style={{ height: 600 }}>
        <DnDCalendar
          localizer={localizer}
          defaultView="day"
          defaultDate={new Date(2030, 0, 7)}
          events={events}
          resources={resources}
          resourceIdAccessor={(r) => (r as (typeof resources)[number]).id}
          resourceTitleAccessor={(r) => (r as (typeof resources)[number]).title}
          onEventDrop={vi.fn()}
          onEventResize={vi.fn()}
        />
      </div>,
    );
    expect(screen.getByText("Sam Tech")).toBeInTheDocument();
    expect(screen.getByText("Alex Tech")).toBeInTheDocument();
    expect(screen.getByText("#101 Acme")).toBeInTheDocument();
    expect(screen.getByText("#102 Globex")).toBeInTheDocument();
    expect(container.querySelector(".rbc-addons-dnd")).not.toBeNull();
    const bad = errors.mock.calls.filter((c) => /Warning|Error/.test(String(c[0])));
    expect(bad).toEqual([]);
    errors.mockRestore();
  });
});
