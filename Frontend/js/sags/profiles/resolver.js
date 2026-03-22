import { createArticle15Profile } from "./article15.js";
import { createArticle18Profile } from "./article18.js";
import { createArticle19Profile } from "./article19.js";
import { createGenericProfile } from "./generic.js";

export function resolveDecisionProfile(parsedArticle) {
  const article = Number(parsedArticle && parsedArticle.article);
  const section = Number(parsedArticle && parsedArticle.section);
  if (article === 15 && (section === 1 || section === 2)) {
    return createArticle15Profile(section);
  }
  if (article === 18) {
    return createArticle18Profile();
  }
  if (article === 19) {
    return createArticle19Profile();
  }
  return createGenericProfile(article, section);
}
