import { gql } from "@apollo/client/core";

/**
 * Benachrichtigung wenn irgendein Projekt geändert wird (class-level).
 * Für die Listenansicht: bei jeder Änderung refetch auslösen.
 *
 * Backend-generierter Name: onProjektClassChange (general_manager)
 */
export const PROJEKT_LISTE_SUBSCRIPTION = gql`
  subscription ProjektListeUpdated {
    onProjektClassChange {
      action
    }
  }
`;

export const PROJEKT_DETAIL_SUBSCRIPTION = gql`
  subscription ProjektUpdated($id: ID!) {
    onProjektChange(id: $id) {
      action
      item {
        id
        name
        auftragsnummer
        offerteSumme {
          value
          unit
        }
        wvSumme {
          value
          unit
        }
        auftragFertig
        projektleiter
      }
    }
  }
`;
