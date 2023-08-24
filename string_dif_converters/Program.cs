using System.Linq.Expressions;
using System.Runtime.InteropServices;

namespace string_dif_converters
{
    internal class Program
    // PUSH FOR SATAN
    {
        static void Main(string[] args)
        {
            bool running = true;

            while (running)
            {
                Console.WriteLine("Vælg en funktion");
                Console.WriteLine("1. Baglæns sætning");
                Console.WriteLine("2. Konverter bogstaver");
                Console.WriteLine("3. Erstart {{navn}} med et valgt navn");
                Console.WriteLine("4. Sætning med job, age, and education");
                Console.WriteLine("5. 2 Dictionary Metode");
                Console.WriteLine("6. Afslut");

                try
                {

                    int valg = Convert.ToInt32(Console.ReadLine());

                    switch (valg)
                    {
                        case 1:
                            Console.WriteLine("Skriv en sætning");
                            string input = Console.ReadLine();
                            switcharoo(input);
                            break;

                        case 2:
                            Console.WriteLine("Skriv en sætning");
                            string inputSentence = Console.ReadLine();

                            Console.WriteLine("Vælg et bogstav, du vil erstatte");
                            char oldChar = Console.ReadKey().KeyChar;

                            Console.WriteLine("\nVælg det nye bogstav");
                            char newChar = Console.ReadKey().KeyChar;

                            string modifiedSentence = erstatBogstav(inputSentence, oldChar, newChar);
                            Console.WriteLine("\nÆndret sætning: " + modifiedSentence);
                            break;


                        case 3:
                            var people = new Dictionary<int, string>
                            {
                                {1, "Anders"},
                                {2, "Anton"},
                                {3, "Ariel"},
                                {4, "Marcus"},
                                {5, "Mikkel"},
                                {6, "Mogens"},
                                {7, "Lille Virgil"}
                            };
                            Console.WriteLine("Du skal nu vælge et navn: \n");
                            foreach (var person in people)
                            {
                                Console.WriteLine($"{person.Key} {person.Value}");
                            }
                            int chosenPeopleKey = Convert.ToInt32(Console.ReadLine());
                            string chosenPersonName = "";

                            if (people.ContainsKey(chosenPeopleKey))
                            {
                                chosenPersonName = people[chosenPeopleKey];

                            }
                            Console.WriteLine("Du skal nu skrive en sætning hvor {{navn}} er placeret");
                            //string answer = Console.ReadLine().ToLower();

                            string sentence = Console.ReadLine();
                            sentence = sentence.Replace("{{navn}}", chosenPersonName);
                            Console.WriteLine(sentence);


                            //skriv din sætning med {{navn}}
                            break;

                        case 4:
                            Dictionary<string, string> placeholders = new Dictionary<string, string>
                            {
                                {"{{job}}", "programmer"},
                                {"{{edu}}", "Harvard"},
                                {"{{age}}", "32"}
                            };

                            Console.WriteLine("Du kan skrive en sætning med {{job}}, {{age}}, {{edu}}, og sætningnen blive genereret automatisk");
                            string sentenceOfUsers = Console.ReadLine();

                            foreach (var placeholder in placeholders)
                            {
                                sentenceOfUsers = sentenceOfUsers.Replace(placeholder.Key, placeholder.Value);
                            }
                            Console.WriteLine(sentenceOfUsers);

                            break;

                        case 5:
                            // metode 2 dictionarys 

                            Console.WriteLine("Du skal nu vælge 1. for stillesidende arbejde, eller 2. for fysisk arbejde");
                            string input2 = Console.ReadLine();
                            string result2 = TwoDictionaryMethod(input2);

                            Console.WriteLine(result2);
                            break;

                        case 6:
                            // skriv HEj eller HELLO får at få en danskk eller engelsk velkomst. 
                            Console.WriteLine("Hej skriv venligst 'Hej' for dansk. Hi, for english version please type 'Hello'");
                            string input3 = Console.ReadLine();
                            // string result3 = Translator2D(input3);

                            //Console.WriteLine(result3);
                            break;



                        default:
                            Console.WriteLine("Ugyldigt valg");
                            break;
                    }
                }
                catch (FormatException)
                {
                    Console.WriteLine("Ugyldigt input. Vælg venligst en gyldig funktion.");
                }

            }
            // string methods 

            //baglæns sætning
            static void switcharoo(string s)
            {
                string input = Console.ReadLine();
                for (int i = s.Length - 1; i >= 0; i--)
                {
                    Console.Write(s[i]);
                }
                Console.WriteLine();

            }
            // converter bogstaver om til et andet bogstav. 
            static string erstatBogstav(string sentence, char oldChar, char newChar)
            {
                char[] sentenceArray = sentence.ToCharArray();
                for (int i = 0; i < sentenceArray.Length; i++)
                {
                    if (sentenceArray[i] == oldChar)
                    {
                        sentenceArray[i] = newChar;
                    }
                }
                return new string(sentenceArray);
            }

            static string TwoDictionaryMethod(string chosenNumber)
            {
                Dictionary<string, string> placeholders;

                if (chosenNumber == "1")
                {
                    placeholders = new Dictionary<string, string>
                    {
                        {"{{job}}", "programmer"},
                        {"{{edu}}", "Harvard"},
                        {"{{age}}", "32"}
                    };
                }
                else if (chosenNumber == "2")
                {
                    placeholders = new Dictionary<string, string>
                    {
                        {"{{job}}", "Tømrer"},
                        {"{{edu}}", "Selandia Tekniske Skole for Vidunere"},
                        {"{{age}}", "18"}
                    };
                }
                else
                {
                    // Håndter fejlagtig input
                    return "Ugyldigt valg";
                }

                Console.WriteLine("Du kan skrive en sætning med {{job}}, {{age}}, {{edu}}, og sætningen vil blive genereret automatisk");
                string sentenceOfUser = Console.ReadLine();

                foreach (var placeholder in placeholders)
                {
                    sentenceOfUser = sentenceOfUser.Replace(placeholder.Key, placeholder.Value);
                }

                return sentenceOfUser;
            }
            static string Translator2D(string Translation);
            {
                Dictionary<string, Dictionary<string, string>>
            }

        }
    }
}




