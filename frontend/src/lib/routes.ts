/** Route shapes and hash mapping, kept apart from the provider component
 * so both can be unit tested without rendering React.
 */

export type Route =
  | { name: "home" }
  | { name: "teach" }
  | { name: "review"; skillId: string }
  | { name: "practice"; skillId: string }
  | { name: "live"; skillId: string }
  | { name: "verdict"; attemptId: string }
  | { name: "demo" };

export function parseHash(hash: string): Route {
  const clean = hash.replace(/^#\/?/, "");
  const [head, tail] = clean.split("/");
  switch (head) {
    case "teach":
      return { name: "teach" };
    case "review":
      return tail ? { name: "review", skillId: tail } : { name: "home" };
    case "practice":
      return tail ? { name: "practice", skillId: tail } : { name: "home" };
    case "live":
      return tail ? { name: "live", skillId: tail } : { name: "home" };
    case "attempt":
      return tail ? { name: "verdict", attemptId: tail } : { name: "home" };
    case "demo":
      return { name: "demo" };
    default:
      return { name: "home" };
  }
}

export function hashFor(route: Route): string {
  switch (route.name) {
    case "teach":
      return "#/teach";
    case "review":
      return `#/review/${route.skillId}`;
    case "practice":
      return `#/practice/${route.skillId}`;
    case "live":
      return `#/live/${route.skillId}`;
    case "verdict":
      return `#/attempt/${route.attemptId}`;
    case "demo":
      return "#/demo";
    default:
      return "#/";
  }
}
